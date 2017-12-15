from __future__ import print_function

from aci import ImageManifest
from collections import namedtuple
import logging
import os
import signal
from subprograms import ChrtClient, NodeOSClient, resources
import sys

logger = logging.getLogger('nrm')
Container = namedtuple('Container', ['uuid', 'manifest', 'pid'])


class ContainerManager(object):

    """Manages the creation, listing and deletion of containers, using a
    container runtime underneath."""

    def __init__(self, rm):
        self.containers = dict()
        self.pids = dict()
        self.resourcemanager = rm
        self.nodeos = NodeOSClient()
        self.chrt = ChrtClient()

    def create(self, request):
        """Create a container according to the request.

        Returns the pid of the container or a negative number for errors."""
        manifestfile = request['manifest']
        command = request['file']
        args = request['args']
        logger.info("run: manifest file: %s", manifestfile)
        logger.info("run: command:       %s", command)
        logger.info("run: args:          %r", args)
        manifest = ImageManifest()
        if not manifest.load(manifestfile):
            logger.error("Manifest is invalid")
            return -1

        # ask the resource manager for resources
        req = resources(int(manifest.app.isolators.container.cpus.value),
                        int(manifest.app.isolators.container.mems.value))
        allocation = self.resourcemanager.schedule(request['uuid'], req)
        logger.info("run: allocation: %r", allocation)

        # build context to execute
        environ = os.environ
        environ['PATH'] = ("/usr/local/sbin:"
                           "/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
        environ['AC_APP_NAME'] = manifest.name
        environ['AC_METADATA_URL'] = "localhost"
        environ['container'] = 'argo'
        logger.info("run: environ: %r", environ)

        # create container
        container_name = request['uuid']
        logger.info("creating container %s", container_name)
        self.nodeos.create(container_name, allocation)
        logger.info("created container %s", container_name)

        newpid = os.fork()
        logger.info("forked: new pid: %s", newpid)
        if newpid == 0:
            # move myself to that container
            mypid = os.getpid()
            self.nodeos.attach(container_name, mypid)
            logger.info("child: attached to container %s", container_name)

            # run my command
            if hasattr(manifest.app.isolators, 'scheduler'):
                sched = manifest.app.isolators.scheduler
                argv = self.chrt.getwrappedcmd(sched)
            else:
                argv = []

            argv.append(command)
            argv.extend(args)
            logger.debug("execvpe %r", argv)
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
        self.resourcemanager.update(uuid)
        c = self.containers[uuid]
        del self.containers[uuid]
        del self.pids[c.pid]

    def kill(self, uuid):
        """Kill all the processes of a container."""
        if uuid in self.containers:
            c = self.containers[uuid]
            logger.debug("killing %r:", c)
            try:
                os.kill(c.pid, signal.SIGKILL)
            except OSError:
                pass

    def list(self):
        """List the containers in the system."""
        fields = ['uuid', 'pid']
        ret = [c._asdict() for c in self.containers.values()]
        return [{k: d[k] for k in fields} for d in ret]
