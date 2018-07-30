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
        if self.enabled not in ["0", "False", "1", "True"]:
            logger.error("Invalid value of perfwrapper enabled: %s",
                         self.enabled)
            return False
        return True


class PowerPolicy(SpecField):

    """Information on whether to use power policy for a container."""

    policies = ['NONE', 'DDCM', 'DVFS', 'COMBINED']

    fields = {"enabled": spec(unicode, False),
              "policy": spec(unicode, False),
              "damper": spec(unicode, False),
              "slowdown": spec(unicode, False)
              }

    def __init__(self):
        """Create empty perf wrapper."""
        pass

    def load(self, data):
        """Load perf wrapper information."""
        ret = super(PowerPolicy, self).load(data)
        if not ret:
            return ret
        if self.enabled not in ["0", "False", "1", "True"]:
            logger.error("Invalid value of powerpolicy enabled: %s",
                         self.enabled)
            return False
        if self.policy not in self.policies:
            logger.error("Invalid value of powerpolicy policy: %s",
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


class IsolatorList(SpecField):

    """Represent the list of isolator in a Manifest."""

    types = {"argo/scheduler": spec(Scheduler, False),
             "argo/container": spec(Container, True),
             "argo/perfwrapper": spec(PerfWrapper, False),
             "argo/powerpolicy": spec(PowerPolicy, False)
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
                assert name.lstrip("argo/") in self.__dict__
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
