from __future__ import print_function

from aci import ImageManifest
from collections import namedtuple
import logging
from subprograms import ChrtClient, NodeOSClient, resources
import operator

logger = logging.getLogger('nrm')
Container = namedtuple('Container', ['uuid', 'manifest', 'resources',
                                     'power', 'processes', 'clientids',
                                     'hwbindings'])


class ContainerManager(object):

    """Manages the creation, listing and deletion of containers, using a
    container runtime underneath."""

    def __init__(self, rm,
                 perfwrapper="argo-perf-wrapper",
                 linuxperf="perf",
                 argo_nodeos_config="argo_nodeos_config",
                 pmpi_lib="/usr/lib/libnrm-pmpi.so"):
        self.linuxperf = linuxperf
        self.perfwrapper = perfwrapper
        self.nodeos = NodeOSClient(argo_nodeos_config=argo_nodeos_config)
        self.containers = dict()
        self.pids = dict()
        self.resourcemanager = rm
        self.hwloc = rm.hwloc
        self.chrt = ChrtClient()
        self.pmpi_lib = pmpi_lib

    def create(self, request):
        """Create a container according to the request.

        Returns the pid of the container or a negative number for errors."""
        container = None
        containerexistsflag = False
        processes = None
        clientids = None
        pp = None
        hwbindings = None
        bind_index = 0

        manifestfile = request['manifest']
        command = request['file']
        args = request['args']
        environ = request['environ']
        container_name = request['uuid']
        logger.info("run: manifest file:  %s", manifestfile)
        logger.info("run: command:        %s", command)
        logger.info("run: args:           %r", args)
        logger.info("run: container name: %s", container_name)

        # TODO: Application library to load must be set during configuration
        apppreloadlibrary = self.pmpi_lib

        manifest = ImageManifest()
        if not manifest.load(manifestfile):
            logger.error("Manifest is invalid")
            return None

        if manifest.is_feature_enabled('scheduler'):
            sched = manifest.app.isolators.scheduler
            argv = self.chrt.getwrappedcmd(sched)
        else:
            argv = []

        # Check if container exists else create it
        if container_name in self.containers:
            container = self.containers[container_name]
            containerexistsflag = True
            processes = container.processes
            clientids = container.clientids
            hwbindings = container.hwbindings
            bind_index = len(processes)
        else:
            processes = dict()
            clientids = dict()
            hwbindings = dict()

            # ask the resource manager for resources
            ncpus = int(manifest.app.isolators.container.cpus.value)
            nmems = int(manifest.app.isolators.container.mems.value)
            req = resources(ncpus, nmems)
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

            if manifest.is_feature_enabled('power'):
                pp = manifest.app.isolators.power
                if pp.profile in ["1", "True"]:
                    container_power['profile'] = dict()
                    container_power['profile']['start'] = dict()
                    container_power['profile']['end'] = dict()
                if pp.policy != "NONE":
                    container_power['policy'] = pp.policy
                    container_power['damper'] = pp.damper
                    container_power['slowdown'] = pp.slowdown

            # Compute hardware bindings
            if manifest.is_feature_enabled('hwbind'):
                hwbindings['enabled'] = True
                hwbindings['distrib'] = sorted(self.hwloc.distrib(
                                            ncpus, alloc), key=operator.
                                                attrgetter('cpus'))

        # build context to execute
        # environ['PATH'] = ("/usr/local/sbin:"
        #                   "/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
        environ['ARGO_CONTAINER_UUID'] = container_name
        environ['PERF'] = self.linuxperf
        environ['AC_APP_NAME'] = manifest.name
        environ['AC_METADATA_URL'] = "localhost"
        if (containerexistsflag and container.power['policy'] is not None) or (
                pp is not None and pp.policy != "NONE"):
            environ['LD_PRELOAD'] = apppreloadlibrary
            environ['NRM_TRANSMIT'] = '1'
            if containerexistsflag:
                environ['NRM_DAMPER'] = container.power['damper']
            else:
                environ['NRM_DAMPER'] = pp.damper

        # It would've been better if argo-perf-wrapper wrapped around
        # argo-nodeos-config and not the final command -- that way it would
        # be running outside of the container.  However, because
        # argo-nodeos-config is suid root, perf can't monitor it.
        if manifest.is_feature_enabled('perfwrapper'):
            argv.append(self.perfwrapper)

        # Use hwloc-bind to launch each process in the conatiner by prepending
        # it as an argument to the command line, if enabled in manifest.
        # The hardware binding computed using hwloc-distrib is used here
        # --single
        if bool(hwbindings) and hwbindings['enabled']:
            argv.append('hwloc-bind')
            # argv.append('--single')
            argv.append('core:'+str(hwbindings['distrib'][bind_index].cpus[0]))
            argv.append('--membind')
            argv.append('numa:'+str(hwbindings['distrib'][bind_index].mems[0]))

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
                                  processes, clientids, hwbindings)
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
                    p.proc.terminate()
                except OSError:
                    logging.error("OS error: could not terminate process.")

    def list(self):
        """List the containers in the system."""
        return [{'uuid': c.uuid, 'pid': c.processes.keys()}
                for c in self.containers.values()]
