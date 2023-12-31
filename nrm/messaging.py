###############################################################################
# Copyright 2019 UChicago Argonne, LLC.
# (c.f. AUTHORS, LICENSE)
#
# This file is part of the NRM project.
# For more info, see https://xgitlab.cels.anl.gov/argo/nrm
#
# SPDX-License-Identifier: BSD-3-Clause
###############################################################################

import json
import logging
import uuid
import zmq
import zmq.utils
import zmq.utils.monitor
from zmq.eventloop import zmqstream
from schema import loadschema


_logger = logging.getLogger('nrm')
_UpstreamRep = loadschema('json', 'upstreamRep')
_UpstreamPub = loadschema('json', 'upstreamPub')


def send(apiname):
    def wrap(cls):
        model = loadschema('json', apiname)

        def send(self, *args, **kwargs):
            self.socket.send(
                    json.dumps(model(dict(*args, **kwargs))))
        setattr(cls, "send", send)

        return(cls)
    return(wrap)


def recv_callback(apiname):
    def wrap(cls):
        model = loadschema('json', apiname)

        def recv(self):
            """Receives a response to a message."""
            wire = self.socket.recv()
            _logger.debug("received message: %r", wire)
            return model(json.loads(wire))

        def do_recv_callback(self, frames):
            """Receives a message from zmqstream.on_recv, passing it to a user
            callback."""
            _logger.info("receiving message: %r", frames)
            assert len(frames) == 2
            msg = model(json.loads(frames[1]))
            assert self.callback
            self.callback(msg, str(frames[0]))

        def setup_recv_callback(self, callback):
            """Setup a ioloop-backed callback for receiving messages."""
            self.stream = zmqstream.ZMQStream(self.socket)
            self.callback = callback
            self.stream.on_recv(self.do_recv_callback)

        setattr(cls, "recv", recv)
        setattr(cls, "do_recv_callback", do_recv_callback)
        setattr(cls, "setup_recv_callback", setup_recv_callback)

        return(cls)
    return(wrap)


class RPCClient(object):

    """Implements the message layer client to the upstream RPC API."""

    def __init__(self, address):
        self.address = address
        self.uuid = str(uuid.uuid4())
        self.zmq_context = zmq.Context.instance()
        self.socket = self.zmq_context.socket(zmq.DEALER)
        self.socket.setsockopt(zmq.IDENTITY, self.uuid)
        self.socket.setsockopt(zmq.SNDHWM, 0)
        self.socket.setsockopt(zmq.RCVHWM, 0)

    def connect(self, wait=True):
        """Connect, and wait for the socket to be connected."""
        monitor = self.socket.get_monitor_socket()
        self.socket.connect(self.address)
        while wait:
            msg = zmq.utils.monitor.recv_monitor_message(monitor)
            _logger.debug("monitor message: %r", msg)
            if int(msg['event']) == zmq.EVENT_CONNECTED:
                _logger.debug("socket connected")
                break
        self.socket.disable_monitor()


class RPCServer(object):

    """Implements the message layer server to the upstream RPC API."""

    def __init__(self, address):
        self.address = address
        self.zmq_context = zmq.Context.instance()
        self.socket = self.zmq_context.socket(zmq.ROUTER)
        self.socket.setsockopt(zmq.SNDHWM, 0)
        self.socket.setsockopt(zmq.RCVHWM, 0)
        self.socket.bind(address)


@send("upstreamReq")
class UpstreamRPCClient(RPCClient):

    """Implements the message layer client to the upstream RPC API."""

    def recv(self):
        """Receives a response to a message."""
        wire = self.socket.recv()
        _logger.debug("received message: %r", wire)
        return _UpstreamRep(json.loads(wire))


@recv_callback("upstreamReq")
class UpstreamRPCServer(RPCServer):

    """Implements the message layer server to the upstream RPC API."""

    def send(self, client_uuid, *args, **kwargs):
        """Sends a message to the identified client."""
        msg = json.dumps(_UpstreamRep(dict(*args, **kwargs)))
        _logger.debug("sending message: %r to client: %r", msg, client_uuid)
        self.socket.send_multipart([client_uuid, msg])


@send("upstreamPub")
class UpstreamPubServer(object):

    """Implements the message layer server for the upstream PUB/SUB API."""

    def __init__(self, address):
        self.address = address
        self.zmq_context = zmq.Context.instance()
        self.socket = self.zmq_context.socket(zmq.PUB)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.setsockopt(zmq.SNDHWM, 0)
        self.socket.bind(address)


class UpstreamPubClient(object):

    """Implements the message layer client to the upstream Pub API."""

    def __init__(self, address):
        self.address = address
        self.zmq_context = zmq.Context.instance()
        self.socket = self.zmq_context.socket(zmq.SUB)
        self.socket.setsockopt(zmq.RCVHWM, 0)
        self.socket.setsockopt(zmq.SUBSCRIBE, '')

    def connect(self, wait=True):
        """Creates a monitor socket and wait for the connect event."""
        monitor = self.socket.get_monitor_socket()
        self.socket.connect(self.address)
        while wait:
            msg = zmq.utils.monitor.recv_monitor_message(monitor)
            _logger.debug("monitor message: %r", msg)
            if int(msg['event']) == zmq.EVENT_CONNECTED:
                _logger.debug("socket connected")
                break
        self.socket.disable_monitor()

    def recv(self):
        """Receives a message and returns it."""
        frames = self.socket.recv_multipart()
        _logger.debug("received message: %r", frames)
        assert len(frames) == 1
        return _UpstreamPub(json.loads(frames[0]))

    def do_recv_callback(self, frames):
        """Receives a message from zmqstream.on_recv, passing it to a user
        callback."""
        _logger.info("receiving message: %r", frames)
        assert len(frames) == 1
        assert self.callback
        self.callback(_UpstreamPub(json.loads(frames[0])))

    def setup_recv_callback(self, callback):
        """Setup a ioloop-backed callback for receiving messages."""
        self.stream = zmqstream.ZMQStream(self.socket)
        self.callback = callback
        self.stream.on_recv(self.do_recv_callback)


@recv_callback("downstreamEvent")
class DownstreamEventServer(RPCServer):
    pass

    """Implements the message layer server for the downstream event API."""


@send("downstreamEvent")
class DownstreamEventClient(RPCClient):
    pass

    """Implements the message layer client for the downstream event API."""
