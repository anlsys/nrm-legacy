from __future__ import print_function

from aci import ImageManifest
from collections import namedtuple
import logging
import os
from subprograms import ChrtClient, NodeOSClient, resources
import sys

Container = namedtuple('Container', ['uuid', 'manifest', 'pid'])


class ContainerManager(object):

    """Manages the creation, listing and deletion of containers, using a
    container runtime underneath."""

    def __init__(self, rm):
        self.containers = dict()
        self.pids = dict()
        self.logger = logging.getLogger(__name__)
        self.resourcemanager = rm
        self.nodeos = NodeOSClient()
        self.chrt = ChrtClient()

    def create(self, request):
        """Create a container according to the request.

        Returns the pid of the container or a negative number for errors."""
        manifestfile = request['manifest']
        command = request['file']
        args = request['args']
        self.logger.info("run: manifest file: %s", manifestfile)
        self.logger.info("run: command:       %s", command)
        self.logger.info("run: args:          %r", args)
        manifest = ImageManifest()
        if not manifest.load(manifestfile):
            self.logger.error("Manifest is invalid")
            return -1

        # ask the resource manager for resources
        req = resources(int(manifest.app.isolators.container.cpus.value),
                        int(manifest.app.isolators.container.mems.value))
        allocation = self.resourcemanager.schedule(request['uuid'], req)
        self.logger.info("run: allocation: %r", allocation)

        # build context to execute
        environ = os.environ
        environ['PATH'] = ("/usr/local/sbin:"
                           "/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
        environ['AC_APP_NAME'] = manifest.name
        environ['AC_METADATA_URL'] = "localhost"
        environ['container'] = 'argo'
        self.logger.info("run: environ: %r", environ)

        # create container
        container_name = request['uuid']
        self.logger.info("creating container %s", container_name)
        self.nodeos.create(container_name, allocation)
        self.logger.info("created container %s", container_name)

        newpid = os.fork()
        self.logger.info("forked: new pid: %s", newpid)
        if newpid == 0:
            # move myself to that container
            mypid = os.getpid()
            self.nodeos.attach(container_name, mypid)
            self.logger.info("child: attached to container %s", container_name)

            # run my command
            if hasattr(manifest.app.isolators, 'scheduler'):
                sched = manifest.app.isolators.scheduler
                argv = self.chrt.getwrappedcmd(sched)
            else:
                argv = []

            argv.append(command)
            argv.extend(args)
            self.logger.debug("execvpe %r", argv)
            os.execvpe(argv[0], argv, environ)
            # should never happen
            sys.exit(1)
        else:
            c = Container(container_name, manifest, newpid)
            self.pids[newpid] = c
            self.containers[container_name] = c
            return newpid

    def delete(self, uuid):
        """Delete a container and kill all related processes."""
        self.nodeos.delete(uuid, kill=True)
        c = self.containers[uuid]
        del self.containers[uuid]
        del self.pids[c.pid]
