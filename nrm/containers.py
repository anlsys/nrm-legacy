from __future__ import print_function

from aci import ImageManifest
from collections import namedtuple
import logging
import os
from subprograms import ChrtClient, NodeOSClient, resources

logger = logging.getLogger('nrm')
Container = namedtuple('Container', ['uuid', 'manifest', 'process'])


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
            return None

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
        logger.info("run: environ: %r", environ)

        # create container
        container_name = request['uuid']
        environ['ARGO_CONTAINER_UUID'] = container_name
        logger.info("creating container %s", container_name)
        self.nodeos.create(container_name, allocation)
        logger.info("created container %s", container_name)

        # run my command
        if hasattr(manifest.app.isolators, 'scheduler'):
            sched = manifest.app.isolators.scheduler
            argv = self.chrt.getwrappedcmd(sched)
        else:
            argv = []

        # for now we place it within the container, but it's probably better
        # if it's outside (so move it to NodeOSClient?)
        if hasattr(manifest.app.isolators, 'perfwrapper') and hasattr(manifest.app.isolators.perfwrapper, 'enabled') and manifest.app.isolators.perfwrapper.enabled in ["1", "True"]:
            argv.append('argo-perf-wrapper')

        argv.append(command)
        argv.extend(args)
        process = self.nodeos.execute(container_name, argv, environ)
        c = Container(container_name, manifest, process)
        self.pids[process.pid] = c
        self.containers[container_name] = c
        return c

    def delete(self, uuid):
        """Delete a container and kill all related processes."""
        self.nodeos.delete(uuid, kill=True)
        self.resourcemanager.update(uuid)
        c = self.containers[uuid]
        del self.containers[uuid]
        del self.pids[c.process.pid]

    def kill(self, uuid):
        """Kill all the processes of a container."""
        if uuid in self.containers:
            c = self.containers[uuid]
            logger.debug("killing %r:", c)
            try:
                c.process.proc.terminate()
            except OSError:
                pass

    def list(self):
        """List the containers in the system."""
        return [{'uuid': c.uuid, 'pid': c.process.pid} for c in
                self.containers.values()]
