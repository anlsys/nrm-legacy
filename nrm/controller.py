from __future__ import print_function

import logging
import itertools
import numpy

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

    def available_actions(self):
        pass
        # TODO:return all the possible thread commands.

        # ret = []
        # for identity, application in \
                # self.application_manager.applications.iteritems():
            # if target in application.get_allowed_thread_requests():
                # delta = application.get_thread_request_impact(target)
                # ret.append(Action(application, target, delta))
        # return ret

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

class DiscretizedPowerActuator(object):

    """Actuator in charge of power control via discretization."""

    def __init__(self, sm, lowerboundwatts, n):
        self.sensor_manager = sm
        self.lowerboundwatts = lowerboundwatts # the minimal cpu wattage
        self.n = n # the number of arms

    def available_actions(self):
        actions = []
        pl = self.sensor_manager.get_powerlimits()
        logger.info("BanditPowerActuator: power limits %r", pl)
        maxW = int(pl[k]['maxW'])
        if maxW > self.lowerboundwatts:
            logger.error( "BanditPowerActuator: The provided power lowerbound is"\
            "lower than the available maximum CPU wattage.")
        arms = [self.lowerboundwatts + (float(a)*rangeW/float(n)) for a in range(1,n+1)]
        logger.info("BanditPowerActuator: discretized power limits: %r:", arms)
        actions = [Action(target,a,target-a) for a in arms]
        return(actions)

    def execute(self, action):
        logger.info("changing power limit: %r, %r", action.command, action.delta)
        self.sensor_manager.set_powerlimit(action.target, action.command)

    def update(self, action):
        pass


class BasicPowerLoss(object):
    def __init__(self, a, b, power_min, power_max, progress_min, progress_max):
        assert(a < b)
        self.a = a
        self.b = b
        self.power_min = 100000000
        self.power_max = 0
        self.progress_min = 1000000000
        self.progress_max = 0

    def perf(self,progress,power):
        if power>power_max: power_max = power
        if power<power_min: power_min = power
        if progress>progress_max: progress_max = progress
        if progress<progress_min: progress_min = progress
        return((self.a*(power-power_min)/(power_max-power_min)) + 
                (self.b*(progress-progress_min)(progress_max-progress_min)))

class EpsGreedyBandit(object):
    """Epsilon greedy bandit. Actions in O,..,k-1."""

    def __init__(self, epsilon, k):
        assert(k>=1)
        assert(0<=epsilon)
        assert(epsilon<=1)
        self.losses = [0 for a in range(0,k)]
        self.plays = [0 for a in range(0,k)]
        self.a=None
        self.n=0
        self.k=k
        self.eps=epsilon

    def next(self, loss):
        assert(loss >= 0)
        if self.a:
           self.losses[self.a]=self.losses[self.a]+loss
           self.plays[self.a]=self.plays[self.a]+1
        self.n=self.n+1
        if self.n <= self.k:
            self.a = self.n-1
        else:
            if numpy.random.binomial(1,self.epsilon) == 1:
                self.a=numpy.random.randint(0,self.k)
            else:
                self.a=numpy.argmin([self.losses])
        return(self.a)

class BanditController(object):
    """Implements a bandit control loop for resource management."""

    def __init__(self, actuators, initialization_rounds=20, exploration=0.2, enforce=None):
        self.actuators = actuators
        self.initialization_rounds = 20
        self.actions = itertools.product(*[act.available_actions() for a in actuators])
        self.loss = BasicPowerLoss(1,-1)
        self.bandit = EpsGreedyBandit(exploration,len(self.actions))
        self.n=0
        if enforce: 
            assert(enforce>=0)
            assert(enforce<len(self.actions))
        self.enforce=enforce

    def planify(self, target, machineinfo, applications):
        """Plan the next action for the control loop."""
        total_progress = sum([a.progress for a in applications.values()])
        total_power = float(machineinfo['energy']['power']['total'])
        logger.info("Controller: Reading progress %s and power %s." %(total_progress,total_power))
        loss = self.loss(progress=total_progress,power=total_power)
        logger.info("Controller: Computing loss %s." %loss)
        if self.enforce:
            logger.info("Controller: enforced action.")
            a=self.enforce
        if self.n>self.initialization_rounds:
            logger.info("Controller: playing bandit.")
            a=self.bandit.next(loss)
        else:
            logger.info("Controller: estimating max power/max progress ranges.")
            a=self.n % k
        action = self.actions[a]
        logger.info("Controller: playing arm id %a (powercap '%r')." %(a,action.command))
        return(list(action),self.actuators)

    def execute(self, actions, actuators):
        """Build the action for the appropriate manager."""
        for action, actuator in zip(actions,actuators):
            actuator.execute(action)

    def update(self, action, actuator):
        """Update tracking across the board to reflect the last action."""
        for action, actuator in zip(actions,actuators):
            actuator.update(action)
