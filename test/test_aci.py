###############################################################################
# Copyright 2019 UChicago Argonne, LLC.
# (c.f. AUTHORS, LICENSE)
#
# This file is part of the NRM project.
# For more info, see https://xgitlab.cels.anl.gov/argo/nrm
#
# SPDX-License-Identifier: BSD-3-Clause
###############################################################################

"""Tests for the ACI Manifest module."""
import nrm
import nrm.aci
import pytest
import json


@pytest.fixture
def manifest_base_data():
    with open("examples/basic.json") as f:
        return json.load(f)


def test_manifest_disabled_perfwrapper(manifest_base_data):
    """Ensure we can check if a feature is disabled."""
    manifest = nrm.aci.ImageManifest(manifest_base_data)
    assert not manifest.is_feature_enabled("perfwrapper")


def test_enabled_feature(manifest_base_data):
    """Ensure we can check if a feature is enabled without enabled in it."""
    data = manifest_base_data.copy()
    data["app"]["perfwrapper"] = "enabled"
    manifest = nrm.aci.ImageManifest(data)
    assert manifest.is_feature_enabled("perfwrapper")
