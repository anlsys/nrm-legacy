from __future__ import print_function

import logging

logger = logging.getLogger('nrm')


class Action(object):

    """Information about a control action."""

    def __init__(self, target, command):
        self.target = target
        self.command = command


class Controller(object):

    """Implements a control loop for resource management."""

    def __init__(self, am, cm, rm):
        self.application_manager = am
        self.container_manager = cm
        self.resource_manager = rm

    def planify(self, target, machineinfo):
        """Plan the next action for the control loop."""
        total_power = machineinfo['energy']['power']['total']
        if total_power < target:
            for identity, application in \
                    self.application_manager.applications.iteritems():
                if 'i' in application.get_allowed_thread_requests():
                    return Action(application, 'i')
        elif total_power > target:
            for identity, application in \
                    self.application_manager.applications.iteritems():
                if 'd' in application.get_allowed_thread_requests():
                    return Action(application, 'd')
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
