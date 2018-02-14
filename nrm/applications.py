from __future__ import print_function

import logging
import time

logger = logging.getLogger('nrm')


class Application(object):

    """Information about a downstream API user."""

    thread_fsm_table = {'stable': {'i': 's_ask_i', 'd': 's_ask_d'},
                        's_ask_i': {'done': 'stable', 'noop': 'max'},
                        's_ask_d': {'done': 'stable', 'noop': 'min'},
                        'max': {'d': 'max_ask_d'},
                        'min': {'i': 'min_ask_i'},
                        'max_ask_d': {'done': 'stable', 'noop': 'noop'},
                        'min_ask_i': {'done': 'stable', 'noop': 'noop'},
                        'noop': {}}

    def __init__(self, uuid, container, progress, threads):
        self.uuid = uuid
        self.container_uuid = container
        self.progress = progress
        self.threads = threads
        self.thread_state = 'stable'

    def do_thread_transition(self, event):
        """Update the thread fsm state."""
        transitions = self.thread_fsm_table[self.thread_state]
        if event in transitions:
            self.thread_state = transitions[event]

    def get_allowed_thread_requests(self):
        return self.thread_fsm_table[self.thread_state].keys()

    def get_thread_request_impact(self, command):
        # TODO: not a real model
        if command not in self.thread_fsm_table[self.thread_state]:
            return 0.0
        speed = float(self.progress)/float(self.threads['cur'])
        if command == 'i':
            return speed
        else:
            return -speed

    def update_threads(self, msg):
        """Update the thread tracking."""
        newth = msg['payload']
        curth = self.threads['cur']
        if newth == curth:
            self.do_thread_transition('noop')
        else:
            self.do_thread_transition('done')
        self.threads['cur'] = newth

    def update_progress(self, msg):
        """Update the progress tracking."""
        payload = self.progress + float(msg['payload'])

    def reset_progress(self, msg):
        """Update the progress tracking."""
        self.progress = 0

class ApplicationManager(object):

    """Manages the tracking of applications: users of the downstream API."""

    def __init__(self):
        self.applications = dict()

    def register(self, msg):
        """Register a new downstream application."""

        uuid = msg['uuid']
        container = msg['container']
        progress = msg['progress']
        threads = msg['threads']
        self.applications[uuid] = Application(uuid, container, progress,
                                              threads)

    def delete(self, uuid):
        """Delete an application from the register."""
        del self.applications[uuid]
