from __future__ import print_function

import json
import logging
import re
import signal
import zmq
from zmq.eventloop import ioloop, zmqstream
import sensor

application_fsm_table = {'stable': {'i': 's_ask_i', 'd': 's_ask_d'},
                         's_ask_i': {'done': 'stable', 'max': 'max'},
                         's_ask_d': {'done': 'stable', 'min': 'min'},
                         'max': {'d': 'max_ask_d'},
                         'min': {'i': 'min_ask_i'},
                         'max_ask_d': {'done': 'stable', 'min': 'nop'},
                         'min_ask_i': {'done': 'stable', 'max': 'nop'},
                         'nop': {}}


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
        self.buf = ''
        self.logger = logging.getLogger(__name__)
        self.target = 1.0

    def do_application_receive(self, parts):
        self.logger.info("receiving application stream: %r", parts)
        identity = parts[0]

        if len(parts[1]) == 0:
            # empty frame, indicate connect/disconnect
            if identity in self.applications:
                self.logger.info("known client disconnected")
                del self.applications[identity]
            else:
                self.logger.info("new client: " + repr(identity))
                self.applications[identity] = Application(identity)
        else:
            if identity in self.applications:
                application = self.applications[identity]
                # we need to unpack the stream into application messages
                # messages can be: min, max, done (%d), %d
                application.append_buffer(parts[1])
                for m in application.get_messages():
                    application.do_transition(m)
                    self.logger.info("application now in state: %s",
                                     application.state)

    def do_upstream_receive(self, parts):
        self.logger.info("receiving upstream message: %r", parts)
        if len(parts) != 1:
            self.logger.error("unexpected msg length, dropping it: %r", parts)
            return
        msg = json.loads(parts[0])
        if isinstance(msg, dict):
            command = msg.get('command')
            # TODO: switch to a dispatch dictionary
            if command is None:
                self.logger.error("missing command in message: %r", msg)
                return
            if command == 'setpower':
                self.target = float(msg['limit'])
                self.logger.info("new target measure: %g", self.target)
            elif command == 'run':
                self.logger.info("new container required: %r", msg)
            else:
                self.logger.error("invalid command: %r", command)

    def do_sensor(self):
        self.machine_info = self.sensor.do_update()
        self.logger.info("current state: %r", self.machine_info)
        total_power = self.machine_info['energy']['power']['total']
        msg = {'type': 'power',
               'total': total_power,
               'limit': self.target
               }
        self.upstream_pub.send_json(msg)
        self.logger.info("sending sensor message: %r", msg)

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
            self.logger.info("application now in state: %s", application.state)

    def do_signal(self, signum, frame):
        ioloop.IOLoop.current().add_callback_from_signal(self.do_shutdown)

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

        self.logger.info("downstream socket bound to: %s",
                         downstream_bind_param)
        self.logger.info("upstream pub socket bound to: %s",
                         upstream_pub_param)
        self.logger.info("upstream sub socket connected to: %s",
                         upstream_sub_param)

        # register socket triggers
        self.downstream = zmqstream.ZMQStream(downstream_socket)
        self.downstream.on_recv(self.do_application_receive)
        self.upstream_sub = zmqstream.ZMQStream(upstream_sub_socket)
        self.upstream_sub.on_recv(self.do_upstream_receive)
        # create a stream to let ioloop deal with blocking calls on HWM
        self.upstream_pub = zmqstream.ZMQStream(upstream_pub_socket)

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

        ioloop.IOLoop.current().start()


def runner():
    ioloop.install()
    logging.basicConfig(level=logging.DEBUG)
    daemon = Daemon()
    daemon.main()
