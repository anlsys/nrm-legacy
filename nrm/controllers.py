###############################################################################
# Copyright 2019 UChicago Argonne, LLC.
# (c.f. AUTHORS, LICENSE)
#
# This file is part of the NRM project.
# For more info, see https://xgitlab.cels.anl.gov/argo/nrm
#
# SPDX-License-Identifier: BSD-3-Clause
###############################################################################

from __future__ import print_function

import logging
import time
from scipy.integrate import trapz

from nrm.messaging import MSGTYPES
PUB_MSG = MSGTYPES['up_pub']

logger = logging.getLogger('nrm')


class DDCMController(object):

    def __init__(self):
        pass

    def run_policy_container(self, container, application):
        """run policies on a container."""
        ids = container.resources.cpus
        pcs = application.phase_contexts
        # Run policy only if all phase contexts have been received
        if not filter(lambda i: not pcs[i]['set'], ids):
            # Only run policy if all phase contexts are an
            # aggregation of same number of phases
            aggs = [pcs[i]['aggregation'] for i in ids]
            if aggs.count(aggs[0]) == len(aggs):
                container.power['manager'].run_policy(pcs)
                if filter(lambda i: pcs[i]['set'], ids):
                    logger.debug("Phase context not reset %r", application)
            else:
                container.power['manager'].reset_all()
                for i in ids:
                    pcs[i]['set'] = False


class NodePowerController(object):

    """Implements a control loop for power capping."""

    def __init__(self,
                 upstream_pub_server,
                 powercap,
                 sensor_manager,
                 upstream_pub,
                 period):
        self.upstream_pub_server = upstream_pub_server
        self.upstream_pub = upstream_pub
        self.sensor_manager = sensor_manager
        self.period = period  # control period length
        self.power_ts = []  # power time series
        self.perf_ts = []  # performance time series
        self.last_action = powercap  # initial powercap
        self.last_time = time.time()  # time of last action

    def step_ready(self):
        def ready(ts):
            if len(ts) > 0:
                return ((ts[-1][0] > self.last_time + self.period)
                        and len(ts) > 1)
            else:
                return False
        return(ready(self.power_ts) and ready(self.perf_ts))

    def integrate_and_drop(self, t_now):
        def filter_ts(ts):
            return([(t, x) for (t, x) in ts if t >= self.last_time])

        def integrate(ts):
            return(trapz([x[1] for x in ts],
                         [x[0] for x in ts]))

        def spantime(ts): return(ts[-1][0] - ts[0][0])

        power_ts = filter_ts(self.power_ts)
        perf_ts = filter_ts(self.perf_ts)
        perf = integrate(perf_ts)
        power = integrate(power_ts)
        t_power = spantime(power_ts)
        t_perf = spantime(perf_ts)

        self.power_ts = [self.power_ts[-1]]
        self.perf_ts = [self.perf_ts[-1]]
        return(perf, power, t_power, t_perf)

    def feed_power(self, v):
        self.power_ts.append((time.time(), v))

    def feed_performance(self, v):
        self.perf_ts.append((time.time(), v))

    def step(self):
        if self.step_ready():
            logger.info("ready to control")
            now = time.time()
            perf, power, t_power, t_perf = self.integrate_and_drop(now)
            perfvalue = float(perf)/float(t_perf)
            powervalue = float(power)/float(t_power)
            self.publish(self.last_action,
                         perfvalue,
                         powervalue,
                         self.last_time,
                         now)
        else:
            logger.info("wasn't ready to control")
            logger.info(self.power_ts)
            logger.info(self.perf_ts)

    def command(self, cap):
        domains = ['package-0', 'package-1']
        logger.info("GET:")
        logger.info(self.sensor_manager.rapl.get_powerlimits())
        for domain in domains:
            logger.info("Setting powercap on domain %s to %d", domain, cap)
            self.sensor_manager.set_powerlimit(domain, cap)

    def publish(self, cap, power, perf, time1, time2):
        pub = {'api': 'up_pub',
               'type': 'control',
               'powercap': cap,
               'power': power,
               'performance': perf,
               'control_time': time1,
               'feedback_time': time2}
        self.upstream_pub_server.sendmsg(PUB_MSG['control'](**pub))
