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

    def __init__(self, uuid, container, progress, phase_contexts):
        self.uuid = uuid
        self.container_uuid = container
        self.progress = progress
        self.phase_contexts = phase_contexts

    def update_progress(self, msg):
        """Update the progress tracking."""
        assert self.progress
        logger.info("received progress message: "+str(msg))

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
        self.applications[uuid] = Application(uuid, container_uuid, progress, phase_contexts)

    def delete(self, uuid):
        """Delete an application from the register."""
        del self.applications[uuid]
