"""Tests for the Sensor module."""
import nrm
import nrm.sensor
import pytest


@pytest.fixture
def sensor_manager():
    """Fixture for a regular sensor manager."""
    return nrm.sensor.SensorManager()


def test_sensor_update_returns_valid_data(sensor_manager):
    sensor_manager.start()
    data = sensor_manager.do_update()
    assert 'energy' in data
    assert 'power' in data['energy']
    assert 'total' in data['energy']['power']
