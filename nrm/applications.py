from __future__ import print_function

import logging

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

    def __init__(self, uuid, container, progress, threads, phase_contexts):
        self.uuid = uuid
        self.container_uuid = container
        self.progress = progress
        self.threads = threads
        self.thread_state = 'stable'
        self.phase_contexts = phase_contexts

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
        assert self.progress

    def update_phase_context(self, msg):
        """Update the phase contextual information."""
        id = int(msg['cpu'])
        self.phase_contexts[id] = {k: int(msg[k]) for k in ('startcompute',
                                   'endcompute', 'startbarrier', 'endbarrier')}
        self.phase_contexts[id]['set'] = True


class ApplicationManager(object):

    """Manages the tracking of applications: users of the downstream API."""

    def __init__(self):
        self.applications = dict()

    def register(self, msg, container):
        """Register a new downstream application."""

        uuid = msg['uuid']
        container_uuid = msg['container']
        progress = msg['progress']
        threads = msg['threads']
        phase_contexts = dict()
        phase_context_keys = ['set', 'startcompute', 'endcompute',
                              'startbarrier', 'endbarrier']
        if container.power['policy']:
            ids = container.resources['cpus']
            for id in ids:
                phase_contexts[id] = dict.fromkeys(phase_context_keys)
                phase_contexts[id]['set'] = False
        else:
            phase_contexts = None
        self.applications[uuid] = Application(uuid, container_uuid, progress,
                                              threads, phase_contexts)

    def delete(self, uuid):
        """Delete an application from the register."""
        del self.applications[uuid]
