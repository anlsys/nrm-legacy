from __future__ import print_function

import logging

logger = logging.getLogger('nrm')


class Action(object):

    """Information about a control action."""

    def __init__(self, target, command, delta):
        self.target = target
        self.command = command
        self.delta = delta


class ApplicationActuator(object):

    """Actuator in charge of application thread control."""

    def __init__(self, am, pubstream):
        self.application_manager = am
        self.pubstream = pubstream

    def available_actions(self, target):
        ret = []
        for identity, application in \
                self.application_manager.applications.iteritems():
            if target in application.get_allowed_thread_requests():
                delta = application.get_thread_request_impact(target)
                ret.append(Action(application, target, delta))
        return ret

    def execute(self, action):
        target_threads = action.target.threads
        update = {'type': 'application',
                  'command': 'threads',
                  'uuid': action.target.uuid,
                  'event': 'threads',
                  }
        if action.command == 'i':
            payload = target_threads['cur'] + 1
        elif action.command == 'd':
            payload = target_threads['cur'] - 1
        else:
            assert False, "impossible command"
        update['payload'] = payload
        self.pubstream.send_json(update)

    def update(self, action):
        action.target.do_thread_transition(action.command)


class PowerActuator(object):

    """Actuator in charge of power control."""

    def __init__(self, sm):
        self.sensor_manager = sm

    def available_actions(self, target):
        actions = []
        pl = self.sensor_manager.get_powerlimits()
        logger.info("power limits: %r:", pl)
        for k in pl:
            r = range(int(pl[k]['curW']), int(pl[k]['maxW']))
            actions.extend([Action(k, s, s - r[0]) for s in r])
        return actions

    def execute(self, action):
        self.sensor_manager.set_powerlimit(action.target, action.command)

    def update(self, action):
        pass


class Controller(object):

    """Implements a control loop for resource management."""

    def __init__(self, actuators):
        self.actuators = actuators

    def planify(self, target, machineinfo):
        """Plan the next action for the control loop."""
        total_power = machineinfo['energy']['power']['total']
        direction = None
        if total_power < target:
            direction = 'i'
        elif total_power > target:
            direction = 'd'

        if direction:
            actions = []
            for act in self.actuators:
                newactions = act.available_actions(direction)
                actions.extend([(a, act) for a in newactions])
            if actions:
                # TODO: better choice
                actions.sort(key=lambda x: x[0].delta)
                return actions.pop()
            else:
                return (None, None)

    def execute(self, action, actuator):
        """Build the action for the appropriate manager."""
        actuator.execute(action)

    def update(self, action, actuator):
        """Update tracking across the board to reflect the last action."""
        actuator.update(action)
