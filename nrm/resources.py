from __future__ import print_function

import logging
from subprograms import HwlocClient, resources


class ResourceManager(object):

    """Manages the query of node resources, the tracking of their use and
    the scheduling of new containers according to partitioning rules."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.hwloc = HwlocClient()

        # query the node topo, keep track of the critical resources
        self.allresources = self.hwloc.info()
        self.logger.debug("resource info: %r", self.allresources)
        self.available = self.allresources

    def schedule(self, uuid, request):
        """Schedule a resource request on the available resources.

        Request is a dictionary of the resources asked for."""
        # dumb scheduling, just give the first resources available:
        #  - cpus are exclusive
        #  - memories exclusive if more than one left
        if len(self.available.cpus) >= request.cpus:
            retcpus = self.available.cpus[:request.cpus]
            availcpus = self.available.cpus[request.cpus:]
        else:
            retcpus = []
            availcpus = self.available.cpus
        if len(self.available.mems) > 1:
            retmems = self.available.mems[:request.mems]
            availmems = self.available.mems[request.mems:]
        else:
            retmems = self.available.mems
            availmems = self.available.mems
        self.available = resources(availcpus, availmems)
        return resources(retcpus, retmems)

    def remove(self, uuid):
        """Free the resources associated with request uuid."""
        pass

#    def oldcode(self):
#        numcpus = int(manifest.app.isolators.container.cpus.value)
#
#        allresources = hwloc.info()
#        self.logger.debug("resource info: %r", allresources)
#        ncontainers = len(allresources.cpus) // numcpus
#        self.logger.debug("will support %s containers", ncontainers)
#        cur = nodeos.getavailable()
#        self.logger.debug("%r are available", cur)
#        sets = hwloc.distrib(ncontainers, restrict=cur, fake=allresources)
#        self.logger.info("asking for %s cores", numcpus)
#        self.logger.debug("will search in one of these: %r", sets)
#        # find a free set
#        avail = set(cur.cpus)
#        for s in sets:
#            cpuset = set(s.cpus)
#            if cpuset.issubset(avail):
#                alloc = s
#                break
#        else:
#            self.logger.error("no exclusive cpuset found among %r", avail)
#            return -2
#
