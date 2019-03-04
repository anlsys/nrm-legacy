###############################################################################
# Copyright 2019 UChicago Argonne, LLC.
# (c.f. AUTHORS, LICENSE)
#
# This file is part of the NRM project.
# For more info, see https://xgitlab.cels.anl.gov/argo/nrm
#
# SPDX-License-Identifier: BSD-3-Clause
###############################################################################

from __future__ import print_function

from applications import ApplicationManager
from containers import ContainerManager, NodeOSRuntime
from controllers import DDCMController, NodePowerController
from powerpolicy import PowerPolicyManager
from functools import partial
import logging
import os
from resources import ResourceManager
from sensor import SensorManager
import signal
from zmq.eventloop import ioloop
from nrm.messaging import MSGTYPES
from nrm.messaging import UpstreamRPCServer, UpstreamPubServer, \
        DownstreamEventServer

RPC_MSG = MSGTYPES['up_rpc_rep']
PUB_MSG = MSGTYPES['up_pub']

logger = logging.getLogger('nrm')


class Daemon(object):

    def __init__(self, config):
        self.target = 100.0
        self.config = config

    def do_downstream_receive(self, msg, client):
        logger.info("receiving downstream message: %r", msg)
        if msg.type == 'application_start':
            cid = msg.container_uuid
            container = self.container_manager.containers[cid]
            self.application_manager.register(msg, container)
        elif msg.type == 'progress':
            if msg.application_uuid in self.application_manager.applications:
                app = self.application_manager.applications[
                        msg.application_uuid]
                app.update_performance(msg)
                pub = {'api': 'up_pub',
                       'type': 'progress',
                       'payload': msg.payload,
                       'application_uuid': msg.application_uuid}
                self.upstream_pub_server.sendmsg(
                        PUB_MSG['progress'](**pub))
        elif msg.type == 'performance':
            if msg.application_uuid in self.application_manager.applications:
                app = self.application_manager.applications[
                        msg.application_uuid]
                app.update_performance(msg)
            pub = {'api': 'up_pub',
                   'type': 'performance',
                   'payload': msg.payload,
                   'container_uuid': msg.container_uuid}
            self.upstream_pub_server.sendmsg(
                    PUB_MSG['performance'](**pub))
            self.nodepowercontroller.feed_performance(msg.payload)
        elif msg.type == 'phase_context':
            uuid = msg.application_uuid
            if uuid in self.application_manager.applications:
                app = self.application_manager.applications[uuid]
                if bool(self.container_manager.containers):
                    cid = app.container_uuid
                    c = self.container_manager.containers[cid]
                    if c.power['policy']:
                        app.update_phase_context(msg)
                        # Run container policy
                        self.ddcmcontroller.run_policy_container(c, app)
        elif msg.type == 'application_exit':
            uuid = msg.application_uuid
            if uuid in self.application_manager.applications:
                self.application_manager.delete(uuid)
        else:
            logger.error("unknown msg: %r", msg)
            return

    def do_upstream_receive(self, msg, client):
        if msg.type == 'setpower':
            self.target = float(msg.limit)
            logger.info("new target measure: %g", self.target)
            update = {'api': 'up_rpc_rep',
                      'type': 'getpower',
                      'limit': str(self.target)
                      }
            self.upstream_rpc_server.sendmsg(RPC_MSG['getpower'](**update),
                                             client)
        elif msg.type == 'run':
            logger.info("asked to run a command in a container: %r", msg)
            container_uuid = msg.container_uuid
            params = {'manifest': msg.manifest,
                      'file': msg.path,
                      'args': msg.args,
                      'uuid': msg.container_uuid,
                      'environ': msg.environ,
                      'clientid': client,
                      }
            pid, container = self.container_manager.create(params)
            container_uuid = container.uuid
            if len(container.processes) == 1:
                if container.power['policy']:
                    container.power['manager'] = PowerPolicyManager(
                            container.resources.cpus,
                            container.power['policy'],
                            float(container.power['damper']),
                            float(container.power['slowdown']))
                if container.power['profile']:
                    p = container.power['profile']
                    p['start'] = self.machine_info['energy']['energy']
                    p['start']['time'] = self.machine_info['time']
                update = {'api': 'up_pub',
                          'type': 'container_start',
                          'container_uuid': container_uuid,
                          'errno': 0 if container else -1,
                          'power': container.power['policy'] or str(None)
                          }
                self.upstream_pub_server.sendmsg(
                        PUB_MSG['container_start'](**update))

            # now deal with the process itself
            update = {'api': 'up_rpc_rep',
                      'type': 'process_start',
                      'container_uuid': container_uuid,
                      'pid': pid,
                      }
            self.upstream_rpc_server.sendmsg(
                RPC_MSG['process_start'](**update), client)
            # setup io callbacks
            outcb = partial(self.do_children_io, client, container_uuid,
                            'stdout')
            errcb = partial(self.do_children_io, client, container_uuid,
                            'stderr')
            container.processes[pid].stdout.read_until_close(outcb, outcb)
            container.processes[pid].stderr.read_until_close(errcb, errcb)
        elif msg.type == 'kill':
            logger.info("asked to kill container: %r", msg)
            response = self.container_manager.kill(msg.container_uuid)
            # no update here, as it will trigger child exit
        elif msg.type == 'list':
            logger.info("asked for container list: %r", msg)
            response = self.container_manager.list()
            update = {'api': 'up_rpc_rep',
                      'type': 'list',
                      'payload': response,
                      }
            self.upstream_rpc_server.sendmsg(RPC_MSG['list'](**update),
                                             client)
        else:
            logger.error("invalid command: %r", msg.type)

    def do_children_io(self, client, container_uuid, io, data):
        """Receive data from one of the children, and send it down the pipe.

        Meant to be partially defined on a children basis."""
        logger.info("%r received %r data: %r", container_uuid, io, data)
        update = {'api': 'up_rpc_rep',
                  'type': io,
                  'container_uuid': container_uuid,
                  'payload': data or 'eof',
                  }
        self.upstream_rpc_server.sendmsg(RPC_MSG[io](**update), client)

    def do_sensor(self):
        self.machine_info = self.sensor_manager.do_update()
        logger.info("current state: %r", self.machine_info)
        try:
            total_power = self.machine_info['energy']['power']['total']
        except TypeError:
            logger.error("power sensor format malformed, "
                         "can not report power upstream.")
        else:
            self.nodepowercontroller.feed_power(total_power)
            msg = {'api': 'up_pub',
                   'type': 'power',
                   'total': total_power,
                   'limit': self.target
                   }
            self.upstream_pub_server.sendmsg(PUB_MSG['power'](**msg))
            logger.info("sending sensor message: %r", msg)

    def do_control(self):
        self.nodepowercontroller.step()

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

                    # first, send a process_exit
                    msg = {'api': 'up_rpc_rep',
                           'type': 'process_exit',
                           'status': str(status),
                           'container_uuid': container.uuid,
                           }
                    self.upstream_rpc_server.sendmsg(
                            RPC_MSG['process_exit'](**msg), clientid)
                    # Remove the pid of process that is finished
                    container.processes.pop(pid, None)
                    self.container_manager.pids.pop(pid, None)
                    logger.info("Process %s in Container %s has finished.",
                                pid, container.uuid)

                    # if this is the last process in the container,
                    # kill everything
                    if len(container.processes) == 0:
                        # deal with container exit
                        msg = {'api': 'up_pub',
                               'type': 'container_exit',
                               'container_uuid': container.uuid,
                               'profile_data': dict(),
                               }
                        p = container.power
                        if p['policy']:
                            p['manager'].reset_all()
                        if p['profile']:
                            e = p['profile']['end']
                            self.machine_info = self.sensor_manager.do_update()
                            e = self.machine_info['energy']['energy']
                            e['time'] = self.machine_info['time']
                            s = p['profile']['start']
                            # Calculate difference between the values
                            diff = self.sensor_manager.calc_difference(s, e)
                            # Get final package temperature
                            temp = self.machine_info['temperature']
                            diff['temp'] = map(lambda k: temp[k]['pkg'], temp)
                            diff['policy'] = p['policy']
                            if p['policy']:
                                diff['damper'] = float(p['damper'])/1000000000
                                diff['slowdown'] = p['slowdown']
                            diff['nodename'] = self.sensor_manager.nodename
                            logger.info("Container %r profile data: %r",
                                        container.uuid, diff)
                            msg['profile_data'] = diff
                        self.container_manager.delete(container.uuid)
                        self.upstream_pub_server.sendmsg(
                                PUB_MSG['container_exit'](**msg))
            else:
                logger.debug("child update ignored")
                pass

    def do_shutdown(self):
        self.sensor_manager.stop()
        ioloop.IOLoop.current().stop()

    def main(self):
        # Bind address for downstream clients
        bind_address = '*'

        # port for upstream PUB API
        upstream_pub_port = 2345
        # port for upstream RPC API
        upstream_rpc_port = 3456

        # setup application listening socket
        downstream_event_param = "ipc:///tmp/nrm-downstream-event"
        upstream_pub_param = "tcp://%s:%d" % (bind_address, upstream_pub_port)
        upstream_rpc_param = "tcp://%s:%d" % (bind_address, upstream_rpc_port)

        self.downstream_event = DownstreamEventServer(downstream_event_param)
        self.upstream_pub_server = UpstreamPubServer(upstream_pub_param)
        self.upstream_rpc_server = UpstreamRPCServer(upstream_rpc_param)

        logger.info("downstream event socket bound to: %s",
                    downstream_event_param)
        logger.info("upstream pub socket bound to: %s", upstream_pub_param)
        logger.info("upstream rpc socket connected to: %s", upstream_rpc_param)

        # register socket triggers
        self.downstream_event.setup_recv_callback(self.do_downstream_receive)
        self.upstream_rpc_server.setup_recv_callback(self.do_upstream_receive)

        # create managers
        self.resource_manager = ResourceManager(hwloc=self.config.hwloc)
        container_runtime = \
            NodeOSRuntime(self.config.argo_nodeos_config)
        self.container_manager = ContainerManager(
                container_runtime,
                self.resource_manager,
                perfwrapper=self.config.argo_perf_wrapper,
                linuxperf=self.config.perf,
                pmpi_lib=self.config.pmpi_lib,
           )
        self.application_manager = ApplicationManager()
        self.sensor_manager = SensorManager()

        self.ddcmcontroller = DDCMController()
        self.nodepowercontroller = NodePowerController(
                upstream_pub_server=self.upstream_pub_server,
                powercap=self.config.powercap,
                sensor_manager=self.sensor_manager,
                upstream_pub=self.upstream_pub_server,
                period=1
                )

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


def runner(config):
    ioloop.install()

    if config.verbose:
        logger.setLevel(logging.DEBUG)

    if config.nrm_log:
        print("Logging to %s" % config.nrm_log)
        logger.addHandler(logging.FileHandler(config.nrm_log))

    daemon = Daemon(config)
    daemon.main()
