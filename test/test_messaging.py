"""Tests for the Sensor module."""
import nrm
import nrm.messaging
import pytest


@pytest.fixture
def upstream_rpc_client():
    """Fixture for a client handle on the upstream RPC API"""
    return nrm.messaging.UpstreamRPCClient("ipc:///tmp/nrm-pytest-rpc")


@pytest.fixture
def upstream_rpc_server():
    """Fixture for a server handle on the upstream RPC API"""
    return nrm.messaging.UpstreamRPCServer("ipc:///tmp/nrm-pytest-rpc")


@pytest.fixture
def upstream_pub_server():
    """Fixture for a server handle on the upstream PUB API"""
    return nrm.messaging.UpstreamPubServer("ipc:///tmp/nrm-pytest-pub")


@pytest.fixture
def upstream_pub_client():
    """Fixture for a server handle on the upstream PUB API"""
    return nrm.messaging.UpstreamPubClient("ipc:///tmp/nrm-pytest-pub")


@pytest.fixture
def dummy_msg():
    """Fixture for a dummy valid message."""
    d = {'api': 'up_rpc_req', 'type': 'list'}
    return nrm.messaging.MSGTYPES['up_rpc_req']['list'](**d)


@pytest.fixture
def dummy_daemon():
    class _daemon(object):
        def __init__(self):
            self.called = False

        def callback(self, msg, client):
            self.called = True
            self.msg = msg
            self.client = client
    return _daemon()


def test_msg_convertion(dummy_msg):
    m = dummy_msg
    assert nrm.messaging.wire2msg(nrm.messaging.msg2wire(m)) == dummy_msg


def test_rpc_connection(upstream_rpc_client, upstream_rpc_server):
    upstream_rpc_client.wait_connected()


def test_rpc_send_recv(upstream_rpc_client, upstream_rpc_server, dummy_msg):
    upstream_rpc_client.sendmsg(dummy_msg)
    msg, client = upstream_rpc_server.recvmsg()
    assert msg == dummy_msg
    assert client == upstream_rpc_client.uuid
    upstream_rpc_server.sendmsg(dummy_msg, client)
    msg = upstream_rpc_client.recvmsg()
    assert msg == dummy_msg


def test_rpc_server_callback(upstream_rpc_client, upstream_rpc_server,
                             dummy_msg, dummy_daemon):
    upstream_rpc_server.setup_recv_callback(dummy_daemon.callback)
    frames = [upstream_rpc_client.uuid, nrm.messaging.msg2wire(dummy_msg)]
    upstream_rpc_server.do_recv_callback(frames)
    assert dummy_daemon.called
    assert dummy_daemon.msg == dummy_msg
    assert dummy_daemon.client == upstream_rpc_client.uuid


def test_pub_server_send(upstream_pub_server, dummy_msg):
    upstream_pub_server.sendmsg(dummy_msg)


def test_pub_connection(upstream_pub_client, upstream_pub_server):
    upstream_pub_client.wait_connected()


def test_pub_client_recv(upstream_pub_server, upstream_pub_client, dummy_msg):
    upstream_pub_server.sendmsg(dummy_msg)
    msg = upstream_pub_client.recvmsg()
    assert msg == dummy_msg
