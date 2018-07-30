""" Power Policy Module:
    This module provides the interfaces that enable use of policies to control
    processor power using controls available in the processor.
    E.g. Dynamic Duty Cycle Modulation (DDCM), Dynamic Voltage
    and Frequency Scaling (DVFS) and Power capping

    The policies target problems like workload imbalance, memory saturation
    seen very often in parallel applications.

    To mitigate workload imbalance the policies adapt core frequencies to
    workload characteristics through use of core-specific power controls.
    The user can choose from three policies - DDCM, DVFS and a combination of
    DVFS and DDCM to mitiage  workload imbalance in parallel applications that
    use barrier synchronizations.
    The effective frequency of cpus not on the critical path of execution is
    reduced thereby lowering energy with little or no adverse impact on
    performance.

    Additional information:

    Bhalachandra, Sridutt, Allan Porterfield, Stephen L. Olivier, and Jan F.
    Prins. "An adaptive core-specific runtime for energy efficiency." In 2017
    IEEE International Parallel and Distributed Processing Symposium (IPDPS),
    pp. 947-956. 2017.

    Note: Power controls (DVFS, DDCM and power capping) needs to be enabled
    before using these interfaces. Please check your architecture specification
    for supported power contols and related information.
"""
import ddcmpolicy
import logging


logger = logging.getLogger('nrm')


class PowerPolicyManager:
    """ Used for power policy application """

    def __init__(self, cpus=None, policy=None, damper=0.1, slowdown=1.1):
        self.cpus = cpus
        self.policy = policy
        self.damper = damper
        self.slowdown = slowdown

        # Intiliaze all power interfaces
        self.ddcmpolicy = ddcmpolicy.DDCMPolicy()

        # Power levels
        self.maxdclevel = self.ddcmpolicy.maxdclevel
        # TODO: Need to set this value when DVFS policies are added
        self.maxfreqlevel = -1
        self.dclevel = dict.fromkeys(self.cpus, self.maxdclevel)
        self.freqlevel = dict.fromkeys(self.cpus, self.maxfreqlevel)

        # Book-keeping
        self.damperexits = 0
        self.slowdownexits = 0
        self.prevtolalphasetime = 10000.0   # Any large value

    def run_policy(self, cpu, startcompute, endcompute, startbarrier,
                   endbarrier):
        # Run only if policy is specified
        if self.policy:
            if cpu not in self.cpus:
                logger.info("""Attempt to change power of cpu not in container
                            : %r""", cpu)
                return
            # Select and invoke appropriate power policy
            # TODO: Need to add a better policy selection logic in addition to
            # user specified using manifest file
            ret, value = self.invoke_policy(cpu, self.policy,
                                            self.dclevel[cpu],
                                            self.freqlevel[cpu], startcompute,
                                            endcompute, startbarrier,
                                            endbarrier)
            if self.policy == 'DDCM' and ret in ['DDCM', 'SLOWDOWN']:
                self.dclevel[cpu] = value

    def invoke_policy(self, cpu, policy, dclevel, freqlevel, startcompute,
                      endcompute, startbarrier, endbarrier):
        # Calculate time spent in computation, barrier in current phase along
        # with total phase time
        computetime = endcompute - startcompute
        barriertime = endbarrier - startbarrier
        totalphasetime = computetime + barriertime

        # If the current phase length is less than the damper value, then do
        # not use policy. This avoids use of policy during startup operation
        # insignificant phases
        if totalphasetime < self.damper:
            self.damperexits += 1
            return 'DAMPER', -1

        # Reset value for next phase
        self.prevtolalphasetime = totalphasetime

        # If the current phase has slowed down beyond the threshold set, then
        # reset power. This helps correct error in policy application or acts
        # as a rudimentary way to detect phase change
        if(dclevel < self.ddcmpolicy.maxdclevel and totalphasetime >
                self.slowdown * self.prevtolalphasetime):
            self.ddcmpolicy.dc.reset(cpu)
            newdclevel = self.ddcmpolicy.maxdclevel

            return 'SLOWDOWN', newdclevel

        # Invoke the correct policy based on operation module
        if policy == "DDCM":
            newdclevel = self.ddcmpolicy.execute(cpu, dclevel, computetime,
                                                 totalphasetime)

        # TODO: Add DVFS and Combined policies

            return 'DDCM', newdclevel

    def print_policy_stats(self, resetflag=False):
        # Get statistics for policy run
        print('PowerPolicyManager: DamperExits %d SlowdownExits %d' %
              (self.damperexits, self.slowdownexits))
        self.ddcmpolicy.print_stats(resetflag)

        if resetflag:
            self.damperexits = 0
            self.slowdownexits = 0

    def power_reset(self, cpu):
        # Reset all power controls
        self.ddcmpolicy.dc.reset(cpu)

        self.dclevel[cpu] = self.maxdclevel

    def power_check(self, cpu):
        # Check status of all power controls
        return self.ddcmpolicy.dc.check(cpu)
