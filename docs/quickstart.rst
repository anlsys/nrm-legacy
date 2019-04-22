==========
Quickstart
==========

.. highlight:: bash

Welcome to the quickstart guide for NRM. This document will guide you to get up
and running with running your computational jobs through the node resource
manager daemon.

Install
=======

Container piece
---------------

The NRM code only supports nrm compute containers for now (*TODO singularity
support coming soon*), so you need to install both nrm and our container piece
on the system. On a production machine, this should be done by a sysadmin, and
locally this can be acheived with::

 git clone https://xgitlab.cels.anl.gov/argo/containers.git
 cd containers
 make install

NRM
---

The NRM core component can be installed in multiple ways:

using Spack
~~~~~~~~~~~

NRM is *TODO* packaged in the spack mainline::

 spack install nrm

using Nix
~~~~~~~~~

NRM has a Nix package in our local package repository::

 nix-env -f "https://xgitlab.cels.anl.gov/argo/argopkgs/-/archive/master/argopkgs-master.tar.gz" -iA nrm

using Pip
~~~~~~~~~

You should be able to get NRM and its dependencies on any machine with::

 pip install git+https://xgitlab.cels.anl.gov/argo/nrm.git

And entering the resulting virtual environment with `pipenv shell`.

Setup: Launching the `nrmd` Daemon
==================================

NRM's behavior is controlled by the `nrmd` userspace daemon. As such, the user
is responsible for starting the daemon in some way. *TODO: what's the
reccomended way*

The daemon is launched via `nrmd` and logs its output to `/tmp/nrm_log` by
default. See `nrmd --help` for additional options.

Running jobs using `nrm`
========================

Tasks are configured using a JSON file called a manifest and started using the `nrm`
command-line utility. Here's an example manifest that allocates two CPUS and
enables power monitoring::

 {
   "acKind": "ImageManifest",
   "acVersion": "0.6.0",
   "name": "test",
   "app": {
     "isolators": [
       {
         "name": "argo/scheduler",
         "value": {
           "policy": "SCHED_OTHER",
           "priority": "0"
         }
       },
       {
         "name": "argo/container",
         "value": {
           "cpus": "2",
           "mems": "1"
         }
       },
       {
         "name": "argo/perfwrapper",
         "value": {
            "enabled": "0"
         }
       },
       {
         "name": "argo/power",
         "value": {
           "enabled": "0",
           "profile": "0",
           "policy": "NONE",
           "damper": "0.1",
           "slowdown": "1.1"
         }
       },
       {
         "name": "argo/monitoring",
         "value": {
            "enabled": "1",
            "ratelimit": "1000000000"
         }
       }
     ]
   }
 }

This manifest can be used in the following way to launch a command::

 nrm run /path/to/manifest.json echo "foobar"

 nrm run /path/to/manifest.json echo "foobar"

You have run your first nrm-enabled command. See the :doc:`manifest
guide <manifest>` for an in-depth description of the manifest file format.
