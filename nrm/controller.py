from __future__ import print_function

import logging
from operator import attrgetter

logger = logging.getLogger('nrm')


class Action(object):

    """Information about a control action."""

    def __init__(self, target, command, delta):
        self.target = target
        self.command = command
        self.delta = delta


class ApplicationActuator(object):

    """Actuator in charge of application thread control."""

    def __init__(self, am):
        self.application_manager = am

    def available_actions(self, target):
        ret = []
        for identity, application in \
                self.application_manager.applications.iteritems():
            if target in application.get_allowed_thread_requests():
                delta = application.get_thread_request_impact(target)
                ret.append(Action(application, target, delta))
        return ret


class Controller(object):

    """Implements a control loop for resource management."""

    def __init__(self, am, cm, rm):
        self.application_manager = am
        self.container_manager = cm
        self.resource_manager = rm
        self.app_actuator = ApplicationActuator(am)

    def planify(self, target, machineinfo):
        """Plan the next action for the control loop."""
        total_power = machineinfo['energy']['power']['total']
        direction = None
        if total_power < target:
            direction = 'i'
        elif total_power > target:
            direction = 'd'

        if direction:
            actions = self.app_actuator.available_actions(direction)
            if actions:
                # TODO: better choice
                actions.sort(key=attrgetter('delta'))
                return actions.pop()
            else:
                return None

    def execute(self, action):
        """Build the action for the appropriate manager."""
        assert action
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
        return update

    def update(self, action, request):
        """Update tracking across the board to reflect the last action."""
        assert action
        action.target.do_thread_transition(action.command)
