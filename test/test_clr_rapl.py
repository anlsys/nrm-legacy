"""Tests for the Coolr RAPL module."""
import nrm
import nrm.coolr
import nrm.coolr.clr_rapl
import pytest


@pytest.fixture
def rapl_reader():
    """Fixture for a regular rapl reader."""
    rr = nrm.coolr.clr_rapl.rapl_reader()
    assert rr.initialized(), "no rapl sysfs detected"
    return rr


def test_read_powerdomains(rapl_reader):
    """Ensure we can read the power domains."""
    assert rapl_reader.get_powerdomains()


def test_get_powerlimits(rapl_reader):
    """Ensure we can read the power limits."""
    data = rapl_reader.get_powerlimits()
    for k in data:
        if data[k]['enabled']:
            break
    else:
        assert False, "No power domain enabled."


def test_set_powerlimits(rapl_reader):
    """Ensure we can set a power limit."""
    data = rapl_reader.get_powerlimits()
    for k in data:
        if data[k]['enabled']:
            # compute a new limit in between cur and max
            newlim = (data[k]['maxW'] - data[k]['curW'])/2.0
    rapl_reader.set_powerlimit_pkg(newlim)


def test_sample(rapl_reader):
    """Ensure we can sample power consumption properly."""
    import time
    rapl_reader.start_energy_counter()
    for i in range(0, 3):
        time.sleep(1)
        assert rapl_reader.sample(accflag=True)
    rapl_reader.stop_energy_counter()
    assert rapl_reader.total_energy_json()
