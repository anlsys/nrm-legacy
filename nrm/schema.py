###############################################################################
# Copyright 2019 UChicago Argonne, LLC.
# (c.f. AUTHORS, LICENSE)
#
# This file is part of the NRM project.
# For more info, see https://xgitlab.cels.anl.gov/argo/nrm
#
# SPDX-License-Identifier: BSD-3-Clause
###############################################################################

import warlock
import json
import os
from jsonschema import Draft4Validator


def loadschema(api):
    sourcedir = os.path.dirname(os.path.realpath(__file__))
    with open(os.path.join(sourcedir, "schemas", api+".json")) as f:
        s = json.load(f)
        Draft4Validator.check_schema(s)
        return(warlock.model_factory(s))
