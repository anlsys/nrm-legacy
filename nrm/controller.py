from __future__ import print_function

import logging
import time
import math

logger = logging.getLogger('nrm')
logger_power = logging.getLogger('power')


class Action(object):

    """Information about a control action."""

    def __init__(self, target, command, delta):
        self.target = target
        self.command = command
        self.delta = delta


class PowerActuator(object):

    """Actuator in charge of power control."""

    def __init__(self, sm):
        self.sensor_manager = sm

    def available_actions(self, target):
        actions = []
        pl = self.sensor_manager.get_powerlimits()
        logger.info("power limits: %r:", pl)
        if target == 'i':
            for k in pl:
                r = range(int(pl[k]['curW'])+1, int(pl[k]['maxW']))
                actions.extend([Action(k, s, s - r[0]) for s in r])
        elif target == 'd':
            for k in pl:
                r = range(1, int(pl[k]['curW']))
                actions.extend([Action(k, s, r[-1] - s) for s in r])
        return actions

    def execute(self, action):
        logger.info("changing power limit. command: %r, delta: %r, target: %r",
                    action.command, action.delta, action.target)
        # sensor_manager is a SensorManager, which is not only about sensing
        # but also about setting power limits.
        self.sensor_manager.set_powerlimit(action.target, action.command)

    def update(self, action):
        pass


class DiscretizedPowerActuator(object):

    """Actuator in charge of power control via discretization."""

    def __init__(self, sm, lowerboundwatts, k):
        self.sensor_manager = sm
        self.lowerboundwatts = lowerboundwatts  # the minimal cpu wattage
        self.k = k  # the number of arms

    def available_actions(self):
        actions = []
        pl = self.sensor_manager.get_powerlimits()
        logger.info("BanditPowerActuator: power limits %r", pl)
        maxW = int(pl[[k for k, i in pl.items()][0]]['maxW'])
        if maxW < self.lowerboundwatts:
            logger.error("BanditPowerActuator: The provided power lowerbound\
                          is higher than the available maximum CPU wattage.")
        rangeW = maxW - self.lowerboundwatts
        arms = [self.lowerboundwatts + (float(a)*rangeW/float(self.k))
                for a in range(1, self.k+1)]
        logger.info("BanditPowerActuator: discretized power limits: %r:", arms)
        actions = [Action([k for k, i in pl.items()][0], int(math.floor(a)), 0)
                   for a in arms]
        return(actions)

    def execute(self, action):
        logger.info("changing power limit: %r, %r",
                    action.command, action.delta)
        self.sensor_manager.set_powerlimit(action.target, action.command)

    def update(self, action):
        pass


class Controller(object):

    """Implements a control loop for resource management."""

    def __init__(self, actuators, strategy):
        self.actuators = actuators

    def planify(self, target, machineinfo):
        """Plan the next action for the control loop."""
        # current_e = float(machineinfo['energy']['energy']
        #                  ['cumulative']['package-0'])/(1000*1000) # in joules
        # In joules:
        current_p = float(machineinfo['energy']['power']['p0'])/(1000*1000)
        current_p = float(machineinfo['energy']['power']['p1'])/(1000*1000)
        logger_power.info("%s %s %s" % (time.time(), current_p, current_p))
        return (None, None)

    def execute(self, action, actuator):
        """Build the action for the appropriate manager."""
        actuator.execute(action)

    def update(self, action, actuator):
        """Update tracking across the board to reflect the last action."""
        actuator.update(action)

    def run_policy(self, containers):
        """Run policies on containers with policies set."""
        for container in containers:
            pp = containers[container].power
            if pp['policy']:
                apps = self.actuators[0].application_manager.applications
                if apps:
                    app = next(apps[a] for a in apps if apps[a].container_uuid
                               == container)
                    ids = containers[container].resources['cpus']
                    # Run policy only if all phase contexts have been received
                    if not filter(lambda i: not app.phase_contexts[i]['set'],
                                  ids):
                        pp['manager'].run_policy(app.phase_contexts)
                        if filter(lambda i: app.phase_contexts[i]['set'], ids):
                            logger.debug("Phase context not reset %r", app)
