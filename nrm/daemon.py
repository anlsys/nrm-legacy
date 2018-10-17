from __future__ import print_function

from applications import ApplicationManager
from containers import ContainerManager
from controller import Controller, ApplicationActuator, PowerActuator
from powerpolicy import PowerPolicyManager
from functools import partial
import json
import logging
import os
from resources import ResourceManager
from sensor import SensorManager
import signal
import zmq
from zmq.eventloop import ioloop, zmqstream


logger = logging.getLogger('nrm')


class Daemon(object):
    def __init__(self):
        self.target = 100.0

    def do_downstream_receive(self, parts):
        logger.info("receiving downstream message: %r", parts)
        if len(parts) != 1:
            logger.error("unexpected msg length, dropping it: %r", parts)
            return
        msg = json.loads(parts[0])
        if isinstance(msg, dict):
            msgtype = msg.get('type')
            event = msg.get('event')
            if msgtype is None or msgtype != 'application' or event is None:
                logger.error("wrong message format: %r", msg)
                return
            if event == 'start':
                cid = msg['container']
                container = self.container_manager.containers[cid]
                self.application_manager.register(msg, container)
            elif event == 'threads':
                uuid = msg['uuid']
                if uuid in self.application_manager.applications:
                    app = self.application_manager.applications[uuid]
                    app.update_threads(msg)
            elif event == 'progress':
                uuid = msg['uuid']
                if uuid in self.application_manager.applications:
                    app = self.application_manager.applications[uuid]
                    app.update_progress(msg)
            elif event == 'phase_context':
                uuid = msg['uuid']
                if uuid in self.application_manager.applications:
                    app = self.application_manager.applications[uuid]
                    c = self.container_manager.containers[app.cid]
                    if c.power['policy']:
                        app.update_phase_context(msg)
            elif event == 'exit':
                uuid = msg['uuid']
                if uuid in self.application_manager.applications:
                    self.application_manager.delete(msg['uuid'])
            else:
                logger.error("unknown event: %r", event)
                return

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
                logger.info("new container will be created if it doesn't "
                            "exist: %r", msg)
                pid, container = self.container_manager.create(msg)
                cid = container.uuid
                clientid = container.clientids[pid]

                # TODO: obviously we need to send more info than that
                update = {'type': 'container',
                          'uuid': cid,
                          'clientid': clientid,
                          'errno': 0 if container else -1,
                          'pid': pid,
                          }

                if len(container.processes.keys()) == 1:
                    update['event'] = 'start'
                    if container.power['policy']:
                        container.power['manager'] = PowerPolicyManager(
                                container.resources['cpus'],
                                container.power['policy'],
                                float(container.power['damper']),
                                float(container.power['slowdown']))
                    if container.power['profile']:
                        p = container.power['profile']
                        p['start'] = self.machine_info['energy']['energy']
                        p['start']['time'] = self.machine_info['time']
                    update['power'] = container.power['policy']

                else:
                    update['event'] = 'process_start'

                # setup io callbacks
                outcb = partial(self.do_children_io, clientid, cid, 'stdout')
                errcb = partial(self.do_children_io, clientid, cid, 'stderr')
                container.processes[pid].stdout.read_until_close(outcb, outcb)
                container.processes[pid].stderr.read_until_close(errcb, errcb)

                self.upstream_pub.send_json(update)
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

    def do_children_io(self, clientid, uuid, io, data):
        """Receive data from one of the children, and send it down the pipe.

        Meant to be partially defined on a children basis."""
        logger.info("%r received %r data: %r", uuid, io, data)
        update = {'type': 'container',
                  'event': io,
                  'uuid': uuid,
                  'clientid': clientid,
                  'payload': data or 'eof',
                  }
        self.upstream_pub.send_json(update)

    def do_sensor(self):
        self.machine_info = self.sensor_manager.do_update()
        logger.info("current state: %r", self.machine_info)
        total_power = self.machine_info['energy']['power']['total']
        msg = {'type': 'power',
               'total': total_power,
               'limit': self.target
               }
        self.upstream_pub.send_json(msg)
        logger.info("sending sensor message: %r", msg)

    def do_control(self):
        plan = self.controller.planify(self.target, self.machine_info)
        action, actuator = plan
        if action:
            self.controller.execute(action, actuator)
            self.controller.update(action, actuator)
        # Call policy only if there are containers
        if self.container_manager.containers:
            self.controller.run_policy(self.container_manager.containers)

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
            if pid in self.container_manager.pids:
                # check if this is an exit
                if os.WIFEXITED(status) or os.WIFSIGNALED(status):
                    container = self.container_manager.pids[pid]
                    clientid = container.clientids[pid]
                    remaining_pids = [p for p in container.processes.keys()
                                      if p != pid]
                    msg = {'type': 'container',
                           'status': status,
                           'uuid': container.uuid,
                           'clientid': clientid,
                           }

                    if not remaining_pids:
                        msg['event'] = 'exit'
                        pp = container.power
                        if pp['policy']:
                            pp['manager'].reset_all()
                        if pp['profile']:
                            e = pp['profile']['end']
                            self.machine_info = self.sensor_manager.do_update()
                            e = self.machine_info['energy']['energy']
                            e['time'] = self.machine_info['time']
                            s = pp['profile']['start']
                            # Calculate difference between the values
                            diff = self.sensor_manager.calc_difference(s, e)
                            # Get final package temperature
                            temp = self.machine_info['temperature']
                            diff['temp'] = map(lambda k: temp[k]['pkg'], temp)
                            logger.info("Container %r profile data: %r",
                                        container.uuid, diff)
                            msg['profile_data'] = diff
                        self.container_manager.delete(container.uuid)
                    else:
                        msg['event'] = 'process_exit'
                        # Remove the pid of process that is finished
                        container.processes.pop(pid, None)
                        self.container_manager.pids.pop(pid, None)
                        logger.info("Process %s in Container %s has finised.",
                                    pid, container.uuid)

                    self.upstream_pub.send_json(msg)
            else:
                logger.debug("child update ignored")
                pass

    def do_shutdown(self):
        self.sensor_manager.stop()
        ioloop.IOLoop.current().stop()

    def main(self):
        # Bind address for downstream clients
        bind_address = '*'

        # PUB port for upstream clients
        upstream_pub_port = 2345
        # SUB port for upstream clients
        upstream_sub_port = 3456

        # setup application listening socket
        context = zmq.Context()
        downstream_pub_socket = context.socket(zmq.PUB)
        downstream_sub_socket = context.socket(zmq.SUB)
        upstream_pub_socket = context.socket(zmq.PUB)
        upstream_sub_socket = context.socket(zmq.SUB)

        downstream_pub_param = "ipc:///tmp/nrm-downstream-out"
        downstream_sub_param = "ipc:///tmp/nrm-downstream-in"
        upstream_pub_param = "tcp://%s:%d" % (bind_address, upstream_pub_port)
        upstream_sub_param = "tcp://%s:%d" % (bind_address, upstream_sub_port)

        downstream_pub_socket.bind(downstream_pub_param)
        downstream_sub_socket.bind(downstream_sub_param)
        downstream_sub_filter = ""
        downstream_sub_socket.setsockopt(zmq.SUBSCRIBE, downstream_sub_filter)
        upstream_pub_socket.bind(upstream_pub_param)
        upstream_sub_socket.bind(upstream_sub_param)
        upstream_sub_filter = ""
        upstream_sub_socket.setsockopt(zmq.SUBSCRIBE, upstream_sub_filter)

        logger.info("downstream pub socket bound to: %s", downstream_pub_param)
        logger.info("downstream sub socket bound to: %s", downstream_sub_param)
        logger.info("upstream pub socket bound to: %s", upstream_pub_param)
        logger.info("upstream sub socket connected to: %s", upstream_sub_param)

        # register socket triggers
        self.downstream_sub = zmqstream.ZMQStream(downstream_sub_socket)
        self.downstream_sub.on_recv(self.do_downstream_receive)
        self.upstream_sub = zmqstream.ZMQStream(upstream_sub_socket)
        self.upstream_sub.on_recv(self.do_upstream_receive)
        # create a stream to let ioloop deal with blocking calls on HWM
        self.upstream_pub = zmqstream.ZMQStream(upstream_pub_socket)
        self.downstream_pub = zmqstream.ZMQStream(downstream_pub_socket)

        # create managers
        self.resource_manager = ResourceManager()
        self.container_manager = ContainerManager(self.resource_manager)
        self.application_manager = ApplicationManager()
        self.sensor_manager = SensorManager()
        aa = ApplicationActuator(self.application_manager, self.downstream_pub)
        pa = PowerActuator(self.sensor_manager)
        self.controller = Controller([aa, pa])

        self.sensor_manager.start()
        self.machine_info = self.sensor_manager.do_update()

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
