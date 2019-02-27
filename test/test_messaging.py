###############################################################################
# Copyright 2019 UChicago Argonne, LLC.
# (c.f. AUTHORS, LICENSE)
#
# This file is part of the NRM project.
# For more info, see https://xgitlab.cels.anl.gov/argo/nrm
#
# SPDX-License-Identifier: BSD-3-Clause
###############################################################################

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
def downstream_event_server():
    """Fixture for a server handle on the downstream event API"""
    return nrm.messaging.DownstreamEventServer("ipc:///tmp/nrm-pytest-down")


@pytest.fixture
def downstream_event_client():
    """Fixture for a client handle on the downstream event API"""
    return nrm.messaging.DownstreamEventClient("ipc:///tmp/nrm-pytest-down")


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
    upstream_rpc_client.connect()


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
    upstream_pub_client.connect()


def test_pub_client_recv(upstream_pub_server, upstream_pub_client, dummy_msg):
    upstream_pub_server.sendmsg(dummy_msg)
    msg = upstream_pub_client.recvmsg()
    assert msg == dummy_msg


def test_down_connection(downstream_event_client, downstream_event_server):
    downstream_event_client.connect()


def test_down_event_send_recv(downstream_event_client, downstream_event_server,
                              dummy_msg):
    downstream_event_client.sendmsg(dummy_msg)
    msg, client = downstream_event_server.recvmsg()
    assert msg == dummy_msg
    assert client == downstream_event_client.uuid


def test_down_event_server_callback(downstream_event_client,
                                    downstream_event_server,
                                    dummy_msg, dummy_daemon):
    downstream_event_server.setup_recv_callback(dummy_daemon.callback)
    frames = [downstream_event_client.uuid, nrm.messaging.msg2wire(dummy_msg)]
    downstream_event_server.do_recv_callback(frames)
    assert dummy_daemon.called
    assert dummy_daemon.msg == dummy_msg
    assert dummy_daemon.client == downstream_event_client.uuid
