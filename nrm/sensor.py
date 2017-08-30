"""Sensor Module:
    provide the core functionalities related to measuring power, energy,
    temperature and other information about the local node, using our internal
    version of the coolr code.

    This module should be the only one interfacing with coolr.
"""
import random


class SensorManager:
    """Performs sensor reading and basic data aggregation."""

    def __init__(self):
        pass

    def do_update(self):
        return {'total_power': random.randrange(0, 34)}
