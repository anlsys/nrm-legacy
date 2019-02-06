"""Tests for the ACI Manifest module."""
import nrm
import nrm.aci
import pytest
import json


@pytest.fixture
def manifest_base_data():
    data = '''{
    "acKind": "ImageManifest",
    "acVersion": "0.6.0",
    "name": "test",
    "app": {
        "isolators": [
            {
                "name": "argo/container",
                "value": {
                    "cpus": "1",
                    "mems": "1"
                }
            }
        ]
        }
}'''
    return json.loads(data)


def test_manifest_disabled_perfwrapper(manifest_base_data):
    """Ensure we can check if a feature is disabled."""
    manifest = nrm.aci.ImageManifest()
    isolator_text = '''{
    "name": "argo/perfwrapper",
    "value": {
        "enabled": "0"
    }
}'''
    isolator = json.loads(isolator_text)
    data = manifest_base_data
    data["app"]["isolators"].append(isolator)
    assert manifest.load_dict(data)
    assert not manifest.is_feature_enabled("perfwrapper")


def test_enabled_feature(manifest_base_data):
    """Ensure we can check if a feature is enabled without enabled in it."""
    manifest = nrm.aci.ImageManifest()
    isolator_text = '''{
    "name": "argo/perfwrapper",
    "value": {}
}'''
    isolator = json.loads(isolator_text)
    data = manifest_base_data
    data["app"]["isolators"].append(isolator)
    assert manifest.load_dict(data)
    assert manifest.is_feature_enabled("perfwrapper")


def test_missing_disabled(manifest_base_data):
    """Ensure that a missing feature doesn't appear enabled."""
    manifest = nrm.aci.ImageManifest()
    assert manifest.load_dict(manifest_base_data)
    assert not manifest.is_feature_enabled("perfwrapper")
