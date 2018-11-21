from __future__ import print_function

from aci import ImageManifest
from collections import namedtuple
import logging
from subprograms import ChrtClient, NodeOSClient, resources
import uuid

logger = logging.getLogger('nrm')
Container = namedtuple('Container', ['uuid', 'manifest', 'resources',
                                     'power', 'processes', 'clientids'])


class ContainerManager(object):

    """Manages the creation, listing and deletion of containers, using a
    container runtime underneath."""

    def __init__(self, rm,
                 perfwrapper="argo-perf-wrapper",
                 linuxperf="perf",
                 argo_nodeos_config="argo_nodeos_config"):
        self.linuxperf = linuxperf
        self.perfwrapper = perfwrapper
        self.nodeos = NodeOSClient(argo_nodeos_config=argo_nodeos_config)
        self.containers = dict()
        self.pids = dict()
        self.resourcemanager = rm
        self.chrt = ChrtClient()

    def create(self, request):
        """Create a container according to the request.

        Returns the pid of the container or a negative number for errors."""
        container = None
        container_name = None
        containerexistsflag = False
        processes = None
        clientids = None

        manifestfile = request['manifest']
        command = request['file']
        args = request['args']
        environ = request['environ']
        ucontainername = request['uuid']
        logger.info("run: manifest file:  %s", manifestfile)
        logger.info("run: command:        %s", command)
        logger.info("run: args:           %r", args)
        logger.info("run: ucontainername: %s", ucontainername)

        # TODO: Application library to load must be set during configuration
        apppreloadlibrary = ''

        manifest = ImageManifest()
        if not manifest.load(manifestfile):
            logger.error("Manifest is invalid")
            return None

        if hasattr(manifest.app.isolators, 'scheduler'):
            sched = manifest.app.isolators.scheduler
            argv = self.chrt.getwrappedcmd(sched)
        else:
            argv = []

        # Check if user-specified container exists else create it
        if ucontainername in self.containers:
                container_name = ucontainername
                container = self.containers[ucontainername]
                containerexistsflag = True
                processes = container.processes
                clientids = container.clientids
        else:
            processes = dict()
            clientids = dict()

            if ucontainername:
                container_name = ucontainername
            else:
                # If no user-specified container name create one
                container_name = str(uuid.uuid4())

            # ask the resource manager for resources
            req = resources(int(manifest.app.isolators.container.cpus.value),
                            int(manifest.app.isolators.container.mems.value))
            alloc = self.resourcemanager.schedule(container_name, req)
            logger.info("run: allocation: %r", alloc)

            # create container
            logger.info("creating container %s", container_name)
            self.nodeos.create(container_name, alloc)
            container_resources = dict()
            container_resources['cpus'], container_resources['mems'] = alloc

            # Container power settings
            container_power = dict()
            container_power['profile'] = None
            container_power['policy'] = None
            container_power['damper'] = None
            container_power['slowdown'] = None
            container_power['manager'] = None

            # It would've been better if argo-perf-wrapper wrapped around
            # argo-nodeos-config and not the final command -- that way it would
            # be running outside of the container.  However, because
            # argo-nodeos-config is suid root, perf can't monitor it.
            if hasattr(manifest.app.isolators, 'perfwrapper'):
                manifest_perfwrapper = manifest.app.isolators.perfwrapper
                if hasattr(manifest_perfwrapper, 'enabled'):
                    if manifest_perfwrapper.enabled in ["1", "True"]:
                        argv.append(self.perfwrapper)

            if hasattr(manifest.app.isolators, 'power'):
                if hasattr(manifest.app.isolators.power, 'enabled'):
                        pp = manifest.app.isolators.power
                        if pp.enabled in ["1", "True"]:
                            if pp.profile in ["1", "True"]:
                                container_power['profile'] = dict()
                                container_power['profile']['start'] = dict()
                                container_power['profile']['end'] = dict()
                            if pp.policy != "NONE":
                                container_power['policy'] = pp.policy
                                container_power['damper'] = pp.damper
                                container_power['slowdown'] = pp.slowdown
                                environ['LD_PRELOAD'] = apppreloadlibrary

        # build context to execute
        # environ['PATH'] = ("/usr/local/sbin:"
        #                   "/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
        environ['ARGO_CONTAINER_UUID'] = container_name
        environ['PERF'] = self.linuxperf
        environ['AC_APP_NAME'] = manifest.name
        environ['AC_METADATA_URL'] = "localhost"

        argv.append(command)
        argv.extend(args)

        # run my command
        process = self.nodeos.execute(container_name, argv, environ)
        processes[process.pid] = process
        clientids[process.pid] = request['clientid']

        if containerexistsflag:
            container.processes[process.pid] = process
            self.pids[process.pid] = container
            logger.info("Created process %s in container %s", process.pid,
                        container_name)
        else:
            container = Container(container_name, manifest,
                                  container_resources, container_power,
                                  processes, clientids)
            self.pids[process.pid] = container
            self.containers[container_name] = container
            logger.info("Container %s created and running : %r",
                        container_name, container)

        return process.pid, container

    def delete(self, uuid):
        """Delete a container and kill all related processes."""
        self.nodeos.delete(uuid, kill=True)
        self.resourcemanager.update(uuid)
        c = self.containers[uuid]
        del self.containers[uuid]
        map(lambda i: self.pids.pop(c.processes[i].pid, None), c.processes)

    def kill(self, uuid):
        """Kill all the processes of a container."""
        if uuid in self.containers:
            c = self.containers[uuid]
            logger.debug("killing %r:", c)
            for p in c.processes.values():
                try:
                    p.terminate()
                except OSError:
                    logging.error("OS error: could not terminate process.")

    def list(self):
        """List the containers in the system."""
        return [{'uuid': c.uuid, 'pid': c.processes.keys()}
                for c in self.containers.values()]
