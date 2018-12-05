from __future__ import print_function

import logging
import time

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
        # self.sensor_manager.set_powerlimit(action.target, action.command)

    def update(self, action):
        pass


class Controller(object):

    """Implements a control loop for resource management."""

    def __init__(self, actuators):
        self.actuators = actuators

    def planify(self, target, machineinfo):
        """Plan the next action for the control loop."""
        # current_e = float(machineinfo['energy']['energy']['cumulative']['package-0'])/(1000*1000) # in joules
        current_p = float(machineinfo['energy']['power']['p0'])/(1000*1000) # in joules
        current_p = float(machineinfo['energy']['power']['p1'])/(1000*1000) # in joules
        logger_power.info("%s %s %s" % (time.time(),current_p,current_p))
        return (None,None)

        # direction = None
        # if total_power < target:
            # direction = 'i'
        # elif total_power > target:
            # direction = 'd'

        # if direction:
            # actions = []
            # for act in self.actuators:
                # newactions = act.available_actions(direction)
                # actions.extend([(a, act) for a in newactions])
            # if actions:
                # # TODO: better choice
                # actions.sort(key=lambda x: x[0].delta)
                # return actions.pop(0)
            # else:
                # return (None, None)

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
