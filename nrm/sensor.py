"""Sensor Module:
    provide the core functionalities related to measuring power, energy,
    temperature and other information about the local node, using our internal
    version of the coolr code.

    This module should be the only one interfacing with coolr.
"""
from __future__ import print_function
import random
import coolr
import coolr.clr_rapl
import coolr.clr_hwmon
import coolr.clr_nodeinfo
import coolr.clr_cpufreq
import coolr.clr_misc


class SensorManager:
    """Performs sensor reading and basic data aggregation."""

    def __init__(self):
        self.nodeconfig = coolr.clr_nodeinfo.nodeconfig()
        self.cputopology = coolr.clr_nodeinfo.cputopology()
        self.coretemp = coolr.clr_hwmon.coretemp_reader()
        self.rapl = coolr.clr_rapl.rapl_reader()

    def start(self):
        self.rapl.start_energy_counter()

    def stop(self):
        self.rapl.stop_energy_counter()

    def do_update(self):
        rapl_data = self.rapl.sample_and_json(accflag=True)
        print(repr(rapl_data))
        hwmon_data = self.coretemp.sample_and_json()
        print(repr(hwmon_data))
        return {'total_power': random.randrange(0, 34)}
