###############################################################################
# Copyright 2019 UChicago Argonne, LLC.
# (c.f. AUTHORS, LICENSE)
#
# This file is part of the NRM project.
# For more info, see https://xgitlab.cels.anl.gov/argo/nrm
#
# SPDX-License-Identifier: BSD-3-Clause
###############################################################################

"""Parse and Represent the APPC ACI specification."""
import collections
import logging
import json

logger = logging.getLogger('nrm')
spec = collections.namedtuple('Field', ['cls', 'required'])


class SpecField(object):

    """Object part of the ACI Image Manifest fields."""

    fields = {}

    def __init__(self):
        """Create empty field."""
        pass

    def load(self, data):
        """Load fields."""
        for key in self.fields:
            spec = self.fields[key]
            if key not in data:
                if spec.required:
                    logger.error("Missing key from manifest: %s", key)
                    return False
            else:
                ok, v = self.loadfield(data[key], spec.cls)
                if not ok:
                    logger.error("Error for key %s in %s", key, self.__class__)
                    return False
                setattr(self, key, v)
        return True

    def loadfield(self, data, cls):
        """load data as if from a field of the provided cls.

        Make sure the basic types are also respected.
        """
        ret = cls()
        if not hasattr(ret, 'load'):
            if not isinstance(data, cls):
                logger.error("Wrong data type %s, expected: %s", cls,
                             data.__class__)
                return (False, None)
            else:
                return (True, data)
        else:
            return (ret.load(data), ret)


class Scheduler(SpecField):

    """Scheduler information for a container."""

    classes = ['SCHED_FIFO', 'SCHED_HPC', 'SCHED_OTHER']

    fields = {"policy": spec(unicode, True),
              "priority": spec(unicode, False),
              "enabled": spec(unicode, False),
              }

    def __init__(self):
        """Create scheduler object."""
        pass

    def load(self, data):
        """Load configuration from json text."""
        ret = super(Scheduler, self).load(data)
        if not ret:
            return ret
        # check scheduler class & prio
        if self.policy not in self.classes:
            logger.error("Wrong scheduling class %s, not any of %r", data,
                         Scheduler.classes)
            return False
        if self.policy != "SCHED_OTHER":
            logger.warning("scheduler priority forced as 0 " +
                           "for non default policies")
            self.priority = "0"
        if getattr(self, "enabled", "1") not in ["0", "False", "1", "True"]:
            logger.error("Invalid value for scheduler enabled: %s",
                         self.enabled)
            return False
        return True


class CPUSet(SpecField):

    """Represent a CPUSet field."""

    def __init__(self):
        """Create an empty set."""
        pass

    def load(self, data):
        """Load from json object."""
        self.value = data
        return True


class MemSet(SpecField):

    """Represent a MemSet field."""

    def __init__(self):
        """Create an empty set."""
        pass

    def load(self, data):
        """Load from json object."""
        self.value = data
        return True


class Container(SpecField):

    """Container Information."""

    fields = {"cpus": spec(CPUSet, True),
              "mems": spec(MemSet, True)
              }

    def __init__(self):
        """Create empty container."""
        pass

    def load(self, data):
        """Load container information."""
        return super(Container, self).load(data)


class PerfWrapper(SpecField):

    """Information on whether to use perf for a container."""

    fields = {"enabled": spec(unicode, False)
              }

    def __init__(self):
        """Create empty perf wrapper."""
        pass

    def load(self, data):
        """Load perf wrapper information."""
        ret = super(PerfWrapper, self).load(data)
        if not ret:
            return ret
        if getattr(self, "enabled", "1") not in ["0", "False", "1", "True"]:
            logger.error("Invalid value for perfwrapper enabled: %s",
                         self.enabled)
            return False
        return True


class Power(SpecField):

    """Power settings for a container."""

    policies = ['NONE', 'DDCM', 'DVFS', 'COMBINED']

    fields = {"enabled": spec(unicode, False),
              "profile": spec(unicode, False),
              "policy": spec(unicode, False),
              "damper": spec(unicode, False),
              "slowdown": spec(unicode, False)
              }

    def __init__(self):
        """Create empty power settings object."""
        pass

    def load(self, data):
        """Load power settings."""
        ret = super(Power, self).load(data)
        if not ret:
            return ret
        if self.enabled not in ["0", "False", "1", "True"]:
            logger.error("Invalid value for power enabled: %s",
                         self.enabled)
            return False
        if self.profile not in ["0", "False", "1", "True"]:
            logger.error("Invalid value for power profile: %s",
                         self.enabled)
            return False
        if self.policy not in self.policies:
            logger.error("Invalid value for power policy: %s",
                         self.policy)
            return False
        if self.damper < 0.0:
            logger.error("Invalid value for power policy damper: %s",
                         self.policy)
            return False
        if self.slowdown < 1.0:
            logger.error("Invalid value for power policy slowdown: %s",
                         self.policy)
            return False
        if self.damper < 0.0:
            logger.error("Invalid value of powerpolicy damper: %s",
                         self.policy)
            return False
        if self.slowdown < 1.0:
            logger.error("Invalid value of powerpolicy slowdown: %s",
                         self.policy)
            return False
        return True


class HwBind(SpecField):

    """Hardware bindings for a container."""

    fields = {"enabled": spec(unicode, False),
              }

    def __init__(self):
        """Create empty hardware bindings  settings object."""
        pass

    def load(self, data):
        """Load hardware bindings settings."""
        ret = super(HwBind, self).load(data)
        if not ret:
            return ret
        if self.enabled not in ["0", "False", "1", "True"]:
            logger.error("Invalid value for hardware bindings enabled: %s",
                         self.enabled)
            return False
        return True


class Monitoring(SpecField):

    """Monitoring options (libnrm)."""

    fields = {"enabled": spec(unicode, False),
              "ratelimit": spec(unicode, False),
              }

    def __init__(self):
        """Create empty monitoring option object."""
        pass

    def load(self, data):
        """Load monitoring options."""
        ret = super(Monitoring, self).load(data)
        if not ret:
            return ret
        if self.enabled not in ["0", "False", "1", "True"]:
            logger.error("Invalid value for monitoring options enabled: %s",
                         self.enabled)
            return False
        if self.ratelimit < 0:
            logger.error("Invalid value for monitoring ratelimit: %s",
                         self.ratelimit)
            return False
        return True


class IsolatorList(SpecField):

    """Represent the list of isolator in a Manifest."""

    types = {"argo/scheduler": spec(Scheduler, False),
             "argo/container": spec(Container, True),
             "argo/perfwrapper": spec(PerfWrapper, False),
             "argo/power": spec(Power, False),
             "argo/hwbind": spec(HwBind, False),
             "argo/monitoring": spec(Monitoring, False),
             }

    def __init__(self):
        """Create empty list."""
        pass

    def load(self, data):
        """Load from json struct."""
        for e in data:
            name = e['name']
            if name in self.types:
                t = self.types[name]
                ok, v = super(IsolatorList, self).loadfield(e['value'], t.cls)
                if not ok:
                    logger.error("Error with %s in %s", name, self.__class__)
                    return False
                setattr(self, name.lstrip("argo/"), v)
        for k in self.types:
            if self.types[k].required:
                if not hasattr(self, k.lstrip("argo/")):
                    logger.error("Missing mandatory isolator: %s", k)
                    return False
        return True


class App(SpecField):

    """Represent the App part of an Image Manifest."""

    # attribute, subclass, required
    fields = {"environment": spec(list, False),
              "isolators": spec(IsolatorList, True),
              }

    def __init__(self):
        """Create empty container."""
        pass

    def load(self, data):
        """Load from json dict."""
        return super(App, self).load(data)


class ImageManifest(SpecField):

    """Represent an ACI Image Manifest."""

    fields = {"acKind": spec(unicode, True),
              "acVersion": spec(unicode, True),
              "name": spec(unicode, True),
              "app": spec(App, True),
              }

    def __init__(self):
        """Create empty manifest."""
        pass

    def load(self, filename):
        """Load a manifest from JSON file."""
        with open(filename, 'r') as f:
            data = json.load(f)
        return super(ImageManifest, self).load(data)

    def load_dict(self, data):
        """Load a manifest in dictionary form."""
        return super(ImageManifest, self).load(data)

    def is_feature_enabled(self, feature, true_values=["1", "True"]):
        """Check if a specific feature is enabled.

        Since the enabled field itself is optional, we return true if an
        isolator is present in a manifest or the enabled field is not true."""
        typename = "argo/{}".format(feature)
        assert typename in IsolatorList.types, \
            "{} in not a valid feature".format(feature)
        logger.debug(repr(self))
        if hasattr(self.app.isolators, feature):
            isolator = getattr(self.app.isolators, feature)
            if hasattr(isolator, 'enabled'):
                if isolator.enabled not in true_values:
                    return False
            return True
        else:
            return False
