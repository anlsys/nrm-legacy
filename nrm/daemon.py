from __future__ import print_function

import logging
import random
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
        self.logger.info("receiving application stream: " + repr(parts))
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
                    self.logger.info("application now in state: " +
                                     application.state)

    def do_sensor(self):
        self.machine_info = self.sensor.do_update()
        self.logger.info("current state: %r" % self.machine_info)

    def do_control(self):
        total_power = self.machine_info['energy']['power']['total']

		# Publish the power values so that GRM can pick it up
        nrm_topic = "23.45"
        self.nrm_publish_sock.send("%s %s" % (nrm_topic, str(total_power)))
        self.logger.info("Sending power values: " + str(total_power))

		# Subcribe to the topic for new power allocations published by the GRM
        # self.target = random.randrange(0, 34)
        string = self.grm_publish_sock.recv()
        topic, self.target = string.split()
        self.logger.info("target measure: " + str(self.target))

        for identity, application in self.applications.iteritems():
            if total_power < self.target:
                if 'i' in application.get_allowed_requests():
                    self.stream.send_multipart([identity, 'i'])
                    application.do_transition('i')
            elif total_power > self.target:
                if 'd' in application.get_allowed_requests():
                    self.stream.send_multipart([identity, 'd'])
                    application.do_transition('d')
            else:
                pass
            self.logger.info("application now in state: " + application.state)

    def do_signal(self, signum, frame):
        ioloop.IOLoop.current().add_callback_from_signal(self.do_shutdown)

    def do_shutdown(self):
        self.sensor.stop()
        ioloop.IOLoop.current().stop()

    def main(self):
        # read config for the port numbers 
        bind_port = 1234
		# NRM publish port is the port to which NRM publishes node power info
        nrm_publish_port = 2345
		# GRM publish port is the port to which GRM publishes the new power allocation
        grm_publish_port = 3456

        bind_address = '*'

        # setup application listening socket
        context = zmq.Context()
        socket = context.socket(zmq.STREAM)
        self.nrm_publish_sock = context.socket(zmq.PUB)
        self.grm_publish_sock = context.socket(zmq.SUB)

        bind_param = "tcp://%s:%d" % (bind_address, bind_port)
        nrm_bind_param = "tcp://%s:%d" % (bind_address, nrm_publish_port)
        grm_bind_param = "tcp://localhost:%d" % (grm_publish_port)

        socket.bind(bind_param)
        self.nrm_publish_sock.bind(nrm_bind_param)
        self.grm_publish_sock.connect(grm_bind_param)
        grm_filter = "34.56 "
        self.grm_publish_sock.setsockopt(zmq.SUBSCRIBE, grm_filter)

        self.logger.info("socket bound to: " + bind_param)
        self.logger.info("NRM publish socket bound to: " + nrm_bind_param)
        self.logger.info("GRM publish socket connected to: " + grm_bind_param)

        self.stream = zmqstream.ZMQStream(socket)
        self.stream.on_recv(self.do_application_receive)

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
