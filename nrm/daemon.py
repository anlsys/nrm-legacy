from __future__ import print_function

from containers import ContainerManager
from resources import ResourceManager
from functools import partial
import json
import logging
import os
import re
import sensor
import signal
import zmq
from zmq.eventloop import ioloop, zmqstream


application_fsm_table = {'stable': {'i': 's_ask_i', 'd': 's_ask_d'},
                         's_ask_i': {'done': 'stable', 'max': 'max'},
                         's_ask_d': {'done': 'stable', 'min': 'min'},
                         'max': {'d': 'max_ask_d'},
                         'min': {'i': 'min_ask_i'},
                         'max_ask_d': {'done': 'stable', 'min': 'nop'},
                         'min_ask_i': {'done': 'stable', 'max': 'nop'},
                         'nop': {}}

logger = logging.getLogger('nrm')


class Application(object):
    def __init__(self, identity):
        self.identity = identity
        self.buf = ''
        self.state = 'stable'

    def append_buffer(self, msg):
        self.buf = self.buf + msg

    def do_transition(self, msg):
        transitions = application_fsm_table[self.state]
        if msg in transitions:
            self.state = transitions[msg]
        else:
            pass

    def get_allowed_requests(self):
        return application_fsm_table[self.state].keys()

    def get_messages(self):
        buf = self.buf
        begin = 0
        off = 0
        ret = ''
        while begin < len(buf):
            if buf.startswith('min', begin):
                ret = 'min'
                off = len(ret)
            elif buf.startswith('max', begin):
                ret = 'max'
                off = len(ret)
            elif buf.startswith('done (', begin):
                n = re.split("done \((\d+)\)", buf[begin:])[1]
                ret = 'done'
                off = len('done ()') + len(n)
            else:
                m = re.match("\d+", buf[begin:])
                if m:
                    ret = 'ok'
                    off = m.end()
                else:
                    break
            begin = begin + off
            yield ret
        self.buf = buf[begin:]
        return


class Daemon(object):
    def __init__(self):
        self.applications = {}
        self.containerpids = {}
        self.buf = ''
        self.target = 1.0

    def do_application_receive(self, parts):
        logger.info("receiving application stream: %r", parts)
        identity = parts[0]

        if len(parts[1]) == 0:
            # empty frame, indicate connect/disconnect
            if identity in self.applications:
                logger.info("known client disconnected")
                del self.applications[identity]
            else:
                logger.info("new client: " + repr(identity))
                self.applications[identity] = Application(identity)
        else:
            if identity in self.applications:
                application = self.applications[identity]
                # we need to unpack the stream into application messages
                # messages can be: min, max, done (%d), %d
                application.append_buffer(parts[1])
                for m in application.get_messages():
                    application.do_transition(m)
                    logger.info("application now in state: %s",
                                application.state)

    def do_upstream_receive(self, parts):
        logger.info("receiving upstream message: %r", parts)
        if len(parts) != 1:
            logger.error("unexpected msg length, dropping it: %r", parts)
            return
        msg = json.loads(parts[0])
        if isinstance(msg, dict):
            command = msg.get('command')
            # TODO: switch to a dispatch dictionary
            if command is None:
                logger.error("missing command in message: %r", msg)
                return
            if command == 'setpower':
                self.target = float(msg['limit'])
                logger.info("new target measure: %g", self.target)
            elif command == 'run':
                logger.info("new container required: %r", msg)
                process = self.container_manager.create(msg)
                self.containerpids[process.pid] = msg['uuid']
                # TODO: obviously we need to send more info than that
                update = {'type': 'container',
                          'event': 'start',
                          'uuid': msg['uuid'],
                          'errno': 0,
                          'pid': process.pid,
                          }
                self.upstream_pub.send_json(update)
                # setup io callbacks
                process.stdout.read_until_close(partial(self.do_children_io,
                                                        msg['uuid'],
                                                        'stdout'))
                process.stderr.read_until_close(partial(self.do_children_io,
                                                        msg['uuid'],
                                                        'stderr'))
            elif command == 'kill':
                logger.info("asked to kill container: %r", msg)
                response = self.container_manager.kill(msg['uuid'])
                # no update here, as it will trigger child exit
            elif command == 'list':
                logger.info("asked for container list: %r", msg)
                response = self.container_manager.list()
                update = {'type': 'container',
                          'event': 'list',
                          'payload': response,
                          }
                self.upstream_pub.send_json(update)
            else:
                logger.error("invalid command: %r", command)

    def do_children_io(self, uuid, io, data):
        """Receive data from one of the children, and send it down the pipe.

        Meant to be partially defined on a children basis."""
        logger.info("%r received %r data: %r", uuid, io, data)
        update = {'type': 'container',
                  'event': io,
                  'uuid': uuid,
                  'payload': data or 'eof',
                  }
        self.upstream_pub.send_json(update)

    def do_sensor(self):
        self.machine_info = self.sensor.do_update()
        logger.info("current state: %r", self.machine_info)
        total_power = self.machine_info['energy']['power']['total']
        msg = {'type': 'power',
               'total': total_power,
               'limit': self.target
               }
        self.upstream_pub.send_json(msg)
        logger.info("sending sensor message: %r", msg)

    def do_control(self):
        total_power = self.machine_info['energy']['power']['total']

        for identity, application in self.applications.iteritems():
            if total_power < self.target:
                if 'i' in application.get_allowed_requests():
                    self.downstream.send_multipart([identity, 'i'])
                    application.do_transition('i')
            elif total_power > self.target:
                if 'd' in application.get_allowed_requests():
                    self.downstream.send_multipart([identity, 'd'])
                    application.do_transition('d')
            else:
                pass
            logger.info("application now in state: %s", application.state)

    def do_signal(self, signum, frame):
        if signum == signal.SIGINT:
            ioloop.IOLoop.current().add_callback_from_signal(self.do_shutdown)
        elif signum == signal.SIGCHLD:
            ioloop.IOLoop.current().add_callback_from_signal(self.do_children)
        else:
            logger.error("wrong signal: %d", signum)

    def do_children(self):
        # find out if children have terminated
        while True:
            try:
                pid, status, rusage = os.wait3(os.WNOHANG)
                if pid == 0 and status == 0:
                    break
            except OSError:
                break

            logger.info("child update %d: %r", pid, status)
            # check if its a pid we care about
            if pid in self.containerpids:
                # check if this is an exit
                if os.WIFEXITED(status) or os.WIFSIGNALED(status):
                    uuid = self.containerpids[pid]
                    self.container_manager.delete(uuid)
                    msg = {'type': 'container',
                           'event': 'exit',
                           'status': status,
                           'uuid': uuid,
                           }
                    self.upstream_pub.send_json(msg)
            else:
                logger.debug("child update ignored")
                pass

    def do_shutdown(self):
        self.sensor.stop()
        ioloop.IOLoop.current().stop()

    def main(self):
        # Bind port for downstream clients
        bind_port = 1234
        # Bind address for downstream clients
        bind_address = '*'
        # PUB port for upstream clients
        upstream_pub_port = 2345
        # SUB port for upstream clients
        upstream_sub_port = 3456

        # setup application listening socket
        context = zmq.Context()
        downstream_socket = context.socket(zmq.STREAM)
        upstream_pub_socket = context.socket(zmq.PUB)
        upstream_sub_socket = context.socket(zmq.SUB)

        downstream_bind_param = "tcp://%s:%d" % (bind_address, bind_port)
        upstream_pub_param = "tcp://%s:%d" % (bind_address, upstream_pub_port)
        upstream_sub_param = "tcp://localhost:%d" % (upstream_sub_port)

        downstream_socket.bind(downstream_bind_param)
        upstream_pub_socket.bind(upstream_pub_param)
        upstream_sub_socket.connect(upstream_sub_param)
        upstream_sub_filter = ""
        upstream_sub_socket.setsockopt(zmq.SUBSCRIBE, upstream_sub_filter)

        logger.info("downstream socket bound to: %s", downstream_bind_param)
        logger.info("upstream pub socket bound to: %s", upstream_pub_param)
        logger.info("upstream sub socket connected to: %s", upstream_sub_param)

        # register socket triggers
        self.downstream = zmqstream.ZMQStream(downstream_socket)
        self.downstream.on_recv(self.do_application_receive)
        self.upstream_sub = zmqstream.ZMQStream(upstream_sub_socket)
        self.upstream_sub.on_recv(self.do_upstream_receive)
        # create a stream to let ioloop deal with blocking calls on HWM
        self.upstream_pub = zmqstream.ZMQStream(upstream_pub_socket)

        # create resource and container manager
        self.resource_manager = ResourceManager()
        self.container_manager = ContainerManager(self.resource_manager)

        # create sensor manager and make first measurement
        self.sensor = sensor.SensorManager()
        self.sensor.start()
        self.machine_info = self.sensor.do_update()

        # setup periodic sensor updates
        self.sensor_cb = ioloop.PeriodicCallback(self.do_sensor, 1000)
        self.sensor_cb.start()

        self.control = ioloop.PeriodicCallback(self.do_control, 1000)
        self.control.start()

        # take care of signals
        signal.signal(signal.SIGINT, self.do_signal)
        signal.signal(signal.SIGCHLD, self.do_signal)

        ioloop.IOLoop.current().start()


def runner():
    ioloop.install()
    logging.basicConfig(level=logging.DEBUG)
    daemon = Daemon()
    daemon.main()
