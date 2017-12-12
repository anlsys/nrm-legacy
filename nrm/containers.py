from __future__ import print_function

from aci import ImageManifest
import logging
import os
from subprograms import ChrtClient, NodeOSClient, HwlocClient
import sys


class ContainerManager(object):

    """Manages the creation, listing and deletion of containers, using a
    container runtime underneath."""

    def __init__(self):
        self.containers = dict()
        self.logger = logging.getLogger(__name__)

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

        chrt = ChrtClient()
        nodeos = NodeOSClient()
        hwloc = HwlocClient()

        # build context to execute
        environ = os.environ
        environ['PATH'] = ("/usr/local/sbin:"
                           "/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
        environ['AC_APP_NAME'] = manifest.name
        environ['AC_METADATA_URL'] = "localhost"
        environ['container'] = 'argo'
        self.logger.info("run: environ: %r", environ)

        # Resource Mapping: the container spec gives us the number of cpus
        # wanted by container.. We compute the number of times we can allocate
        # that inside the system, assuming the container spec to be a valid
        # request. We then use hwloc-distrib to map exclusive sets of cpus for
        # each, and find one set that isn't in use yet.
        # This is not the right way to do it, but it will work for now.
        numcpus = int(manifest.app.isolators.container.cpus.value)

        allresources = hwloc.info()
        self.logger.debug("resource info: %r", allresources)
        ncontainers = len(allresources.cpus) // numcpus
        self.logger.debug("will support %s containers", ncontainers)
        cur = nodeos.getavailable()
        self.logger.debug("%r are available", cur)
        sets = hwloc.distrib(ncontainers, restrict=cur, fake=allresources)
        self.logger.info("asking for %s cores", numcpus)
        self.logger.debug("will search in one of these: %r", sets)
        # find a free set
        avail = set(cur.cpus)
        for s in sets:
            cpuset = set(s.cpus)
            if cpuset.issubset(avail):
                alloc = s
                break
        else:
            self.logger.error("no exclusive cpuset found among %r", avail)
            return -2

        # create container
        container_name = request['uuid']
        self.logger.info("creating container %s", container_name)
        nodeos.create(container_name, alloc)
        self.logger.info("created container %s", container_name)

        newpid = os.fork()
        self.logger.info("forked: new pid: %s", newpid)
        if newpid == 0:
            # move myself to that container
            mypid = os.getpid()
            nodeos.attach(container_name, mypid)
            self.logger.info("child: attached to container %s", container_name)

            # run my command
            if hasattr(manifest.app.isolators, 'scheduler'):
                chrt = ChrtClient(self.config)
                args = chrt.getwrappedcmd(manifest.app.isolators.scheduler)
            else:
                args = []

            args.append(command)
            args.extend(args)
            self.logger.debug("execvpe %r", args)
            os.execvpe(args[0], args, environ)
            # should never happen
            sys.exit(1)
        else:
            return newpid

    def delete(self, uuid):
        """Delete a container and kill all related processes."""
        nodeos = NodeOSClient()
        nodeos.delete(uuid, kill=True)
