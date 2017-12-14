from __future__ import print_function

import argparse
import logging
import signal
import zmq
from zmq.eventloop import ioloop, zmqstream

logger = logging.getLogger('nrm-client')


class Client(object):
    def __init__(self):
        self.buf = ''
        self.nt = 16
        self.max = 32
        self.server = None

    def setup_shutdown(self):
        ioloop.IOLoop.current().add_callback_from_signal(self.do_shutdown)

    def get_server_message(self):
        buf = self.buf
        begin = 0
        ret = ''
        while begin < len(buf):
            if buf[begin] in ['d', 'i', 'n', 'q']:
                ret = buf[begin]
                off = 1
            else:
                break
            begin = begin + off
            yield ret
        self.buf = buf[begin:]
        return

    def do_receive(self, parts):
        logger.info("receive stream: " + repr(parts))

        if len(parts[1]) == 0:
            if self.server:
                # server disconnect, lets quit
                self.setup_shutdown()
                return
            else:
                self.server = parts[0]

        self.buf = self.buf + parts[1]
        for m in self.get_server_message():
            logger.info(m)
            if m == 'd':
                if self.nt == 1:
                    ret = "min"
                else:
                    self.nt -= 1
                    ret = "done (%d)" % self.nt
            elif m == 'i':
                if self.nt == self.max:
                    ret = "max"
                else:
                    self.nt += 1
                    ret = "done (%d)" % self.nt
            elif m == 'n':
                ret = "%d" % self.nt
            elif m == 'q':
                ret = ''
                self.setup_shutdown()
            self.stream.send(self.server, zmq.SNDMORE)
            self.stream.send(ret)

    def do_signal(self, signum, frame):
        logger.critical("received signal: " + repr(signum))
        self.setup_shutdown()

    def do_shutdown(self):
        ioloop.IOLoop.current().stop()

    def main(self):
        # command line options
        parser = argparse.ArgumentParser()
        parser.add_argument("-v", "--verbose",
                            help="verbose logging information",
                            action='store_true')
        parser.add_argument("threads", help="starting number of threads",
                            type=int, default=16)
        parser.add_argument("maxthreads", help="max number of threads",
                            type=int, default=32)
        args = parser.parse_args()

        # deal with logging
        if args.verbose:
            logger.setLevel(logging.DEBUG)
        self.nt = args.threads
        self.max = args.maxthreads

        # read env variables for connection
        connect_addr = "localhost"
        connect_port = 1234
        connect_param = "tcp://%s:%d" % (connect_addr, connect_port)

        # create connection
        context = zmq.Context()
        socket = context.socket(zmq.STREAM)
        socket.connect(connect_param)
        logger.info("connected to: " + connect_param)

        self.stream = zmqstream.ZMQStream(socket)
        self.stream.on_recv(self.do_receive)

        # take care of signals
        signal.signal(signal.SIGINT, self.do_signal)

        ioloop.IOLoop.current().start()


def runner():
    ioloop.install()
    logging.basicConfig(level=logging.INFO)
    client = Client()
    client.main()
