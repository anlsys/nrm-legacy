from __future__ import print_function

import logging
import itertools
import numpy
import math

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

    def __init__(self, sm, lowerboundwatts, k):
        self.sensor_manager = sm
        self.lowerboundwatts = lowerboundwatts # the minimal cpu wattage
        self.k = k # the number of arms

    def available_actions(self):
        actions = []
        pl = self.sensor_manager.get_powerlimits()
        logger.info("BanditPowerActuator: power limits %r", pl)
        maxW = int(pl[[k for k,i in pl.items()][0]]['maxW'])
        if maxW < self.lowerboundwatts:
            logger.error( "BanditPowerActuator: The provided power lowerbound is"\
            "higher than the available maximum CPU wattage.")
        rangeW=maxW-self.lowerboundwatts
        arms = [self.lowerboundwatts + (float(a)*rangeW/float(self.k)) for a in range(1,self.k+1)]
        logger.info("BanditPowerActuator: discretized power limits: %r:", arms)
        actions = [Action([k for k,i in pl.items()][0],int(math.floor(a)),0) for a in arms]
        return(actions)

    def execute(self, action):
        logger.info("changing power limit: %r, %r", action.command, action.delta)
        self.sensor_manager.set_powerlimit(action.target, action.command)

    def update(self, action):
        pass

class BasicPowerLoss(object):
    def __init__(self, alpha, power_max=0, progress_max=0):
        self.alpha = alpha
        self.power_max = power_max
        self.progress_max = progress_max

    def loss(self,progress,power):
        if power>self.power_max: self.power_max = power
        if progress>self.progress_max: self.progress_max = progress
        power_n=power/max(0.001, self.power_max)
        progress_n=progress/max(0.001, self.progress_max)
        return(1. + 0.5 * (self.alpha* power_n + (self.alpha-1)*progress_n))

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
        self.epsilon=epsilon

    def next(self, loss):
        assert(loss >= 0)
        if self.a is not None:
           self.losses[self.a]=self.losses[self.a]+loss
           self.plays[self.a]=self.plays[self.a]+1
        self.n=self.n+1
        logging.info("Bandit: the total plays are:%s" %str(self.plays))
        logging.info("Bandit: the estimated losses are:%s" %str([l/(max(1,p)) for l,p in zip(self.losses,self.plays)]))
        if self.n <= self.k:
            self.a = self.n-1
        else:
            if numpy.random.binomial(1,self.epsilon) == 1:
                self.a=numpy.random.randint(0,self.k)
            else:
                self.a=numpy.argmin([l/float(n) for l,n in zip(self.losses,self.plays)])
        return(self.a)

class BanditController(object):
    """Implements a bandit control loop for resource management."""

    def __init__(self, actuators, initialization_rounds=None,
            exploration=0.2, enforce=None, log_power=None):
        self.actuators = actuators
        self.actions = [a for a in itertools.product(*[act.available_actions() for act in actuators])]
        self.initialization_rounds = len(self.actions)*2
        self.loss = BasicPowerLoss(0.5)
        self.exploration=exploration
        self.bandit = EpsGreedyBandit(exploration,len(self.actions))
        self.last_e=0
        self.n=0
        if enforce is not None: 
            assert(enforce>=0)
            assert(enforce<len(self.actions))
        self.enforce=enforce
        self.log_power=log_power
        if self.log_power is not  None:
            self.log_power.write("progress power loss a desc\n")
            self.log_power.flush()

    def planify(self, target, machineinfo, applications):
        """Plan the next action for the control loop."""
        current_e = float(machineinfo['energy']['energy']['cumulative']['package-0'])/(1000*1000) # in joules
        if self.last_e==0:
            self.last_e=current_e
            return([],[])
        else:
            total_power = current_e - self.last_e
            self.last_e = current_e
        logger.info("Controller: Reading machineinfo %s." %(str(machineinfo)))
        if len(applications)==0:
            self.bandit = EpsGreedyBandit(self.exploration,len(self.actions))
            self.n=0
            if self.log_power is not  None:
                self.log_power.write("new application\n")
                self.log_power.flush()
            return([],[])
        self.n=self.n+1
        total_progress = sum([a.progress for a in applications.values()])
        for a in applications.values():
          a.reset_progress()
        logger.info("Controller: applications %r" %applications.values())
        logger.info("Controller: Reading progress %s and power %s." 
                %(total_progress,total_power))
        loss = self.loss.loss(progress=total_progress,power=total_power)
        logger.info("Controller: Incurring loss %s." %loss)
        if self.enforce is not None:
            logger.info("Controller: enforced action.")
            a=self.enforce
        elif self.n>self.initialization_rounds:
            logger.info("Controller: playing bandit.")
            a=self.bandit.next(loss)
        else:
            logger.info("Controller: estimating max power/max progress ranges.")
            a=self.n % len(self.actions)
        action = self.actions[a]
        logger.info("Controller: playing arm id %s (powercap '%s')." 
                %(str(a),str([act.command for act in list(action)])))
        if self.log_power is not None:
            self.log_power.write("%s %s %s %s %s\n" 
                    %(str(total_progress),str(total_power),str(loss),
                        str(a),str([act.command for act in list(action)])))
            self.log_power.flush()
        return(list(action),self.actuators)

    def execute(self, actions, actuators):
        """Build the action for the appropriate manager."""
        for action, actuator in zip(actions,actuators):
            actuator.execute(action)

    def update(self, actions, actuators):
        """Update tracking across the board to reflect the last action."""
        for action, actuator in zip(actions,actuators):
            actuator.update(action)
