from collections import namedtuple
import json
import logging
import uuid
import zmq
import zmq.utils
import zmq.utils.monitor
from zmq.eventloop import zmqstream

# basestring support
try:
    basestring
except NameError:
    basestring = str

logger = logging.getLogger('nrm')

# list of APIs supported by this messaging layer. Each message is
# indexed by its intended api user and the type of the message, along with
# basic field type information.
APIS = ['up_rpc_req', 'up_rpc_rep', 'up_pub']
MSGFORMATS = {k: {} for k in APIS}
MSGFORMATS['up_rpc_req'] = {'list': {},
                            'run': {'manifest': basestring,
                                    'path': basestring,
                                    'args': list,
                                    'container_uuid': basestring,
                                    'environ': dict},
                            'kill': {'container_uuid': basestring},
                            'setpower': {'limit': basestring},
                            }
MSGFORMATS['up_rpc_rep'] = {'start': {'container_uuid': basestring,
                                      'errno': int,
                                      'pid': int,
                                      'power': dict},
                            'list': {'payload': list},
                            'stdout': {'container_uuid': basestring,
                                       'payload': basestring},
                            'stderr': {'container_uuid': basestring,
                                       'payload': basestring},
                            'exit': {'container_uuid': basestring,
                                     'status': basestring,
                                     'profile_data': dict},
                            'process_start': {'container_uuid': basestring},
                            'process_exit': {'container_uuid': basestring,
                                             'status': basestring},
                            'getpower': {'limit': basestring},
                            }
MSGFORMATS['up_pub'] = {'power': {'total': int, 'limit': float}}

# Mirror of the message formats, using namedtuples as the actual transport
# for users of this messaging layer.
MSGTYPES = {k: {} for k in APIS}
for api, types in MSGFORMATS.items():
    tname = "msg_{}_".format(api)
    MSGTYPES[api] = {k: namedtuple(tname+k, sorted(['api', 'type'] + v.keys()))
                     for k, v in types.items()}


def wire2msg(wire_msg):
    """Convert the wire format into a msg from the available MSGTYPES."""
    fields = json.loads(wire_msg)
    assert 'api' in fields
    api = fields['api']
    assert api in MSGFORMATS
    valid_types = MSGFORMATS[api]
    assert 'type' in fields
    mtype = fields['type']
    assert mtype in valid_types
    # format check
    fmt = valid_types[mtype]
    for key in fields:
        if key in ['api', 'type']:
            continue
        assert key in fmt, "%r missing from %r" % (key, fmt)
        assert isinstance(fields[key], fmt[key]), \
            "type mismatch for %r: %r != %r" % (key, fields[key], fmt[key])
    for key in fmt:
        assert key in fields, "%r missing from %r" % (key, fields)
        assert isinstance(fields[key], fmt[key]), \
            "type mismatch for %r: %r != %r" % (key, fields[key], fmt[key])

    mtuple = MSGTYPES[api][mtype]
    return mtuple(**fields)


def msg2wire(msg):
    """Convert a message to its wire format (dict)."""
    fields = msg._asdict()
    return json.dumps(fields)


class UpstreamRPCClient(object):

    """Implements the message layer client to the upstream RPC API."""

    def __init__(self, address):
        self.address = address
        self.uuid = str(uuid.uuid4())
        self.zmq_context = zmq.Context()
        self.socket = self.zmq_context.socket(zmq.DEALER)
        self.socket.setsockopt(zmq.IDENTITY, self.uuid)
        self.socket.connect(address)

    def wait_connected(self):
        """Creates a monitor socket and wait for the connect event."""
        monitor = self.socket.get_monitor_socket()
        while True:
            msg = zmq.utils.monitor.recv_monitor_message(monitor)
            logger.debug("monitor message: %r", msg)
            if int(msg['event']) == zmq.EVENT_CONNECTED:
                logger.debug("socket connected")
                break
        self.socket.disable_monitor()

    def sendmsg(self, msg):
        """Sends a message, including the client uuid as the identity."""
        self.socket.send(msg2wire(msg))

    def recvmsg(self):
        """Receives a message."""
        wire = self.socket.recv()
        logger.debug("received message: %r", wire)
        return wire2msg(wire)


class UpstreamRPCServer(object):

    """Implements the message layer server to the upstream RPC API."""

    def __init__(self, address):
        self.address = address
        self.zmq_context = zmq.Context()
        self.socket = self.zmq_context.socket(zmq.ROUTER)
        self.socket.bind(address)

    def recvmsg(self):
        """Receives a message and returns it along with the client identity."""
        frames = self.socket.recv_multipart()
        logger.debug("received message: %r", frames)
        assert len(frames) == 2
        msg = wire2msg(frames[1])
        return msg, str(frames[0])

    def do_recv_callback(self, frames):
        """Receives a message from zmqstream.on_recv, passing it to a user
        callback."""
        logger.info("receiving message: %r", frames)
        assert len(frames) == 2
        msg = wire2msg(frames[1])
        assert self.callback
        self.callback(msg, str(frames[0]))

    def sendmsg(self, msg, client_uuid):
        """Sends a message to the identified client."""
        logger.debug("sending message: %r to client: %r", msg, client_uuid)
        self.socket.send_multipart([client_uuid, msg2wire(msg)])

    def setup_recv_callback(self, callback):
        """Setup a ioloop-backed callback for receiving messages."""
        self.stream = zmqstream.ZMQStream(self.socket)
        self.callback = callback
        self.stream.on_recv(self.do_recv_callback)


class UpstreamPubServer(object):

    """Implements the message layer server for the upstream PUB/SUB API."""

    def __init__(self, address):
        self.address = address
        self.zmq_context = zmq.Context()
        self.socket = self.zmq_context.socket(zmq.PUB)
        self.socket.bind(address)

    def sendmsg(self, msg):
        """Sends a message."""
        logger.debug("sending message: %r", msg)
        self.socket.send(msg2wire(msg))