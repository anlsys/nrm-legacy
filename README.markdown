# Argo Node Resource Manager

Resource management daemon using communication with clients to control
power usage of application.

This is a python rewrite of the original code developed for the Argo project
two years ago.

## Requirements

Python dependencies are managed by `pipenv`. You should be able to get the code
running simply with:

> pipenv install

And entering the resulting virtual environment with `pipenv shell`.

The NRM code only supports _argo-containers_ for now, so you need to install
the our container piece on the system for now.

## Basic Usage

Launch the `daemon`, and use `cmd` to interact with it.

## Additional Info

| **Systemwide Power Management with Argo**
| Dan Ellsworth, Tapasya Patki, Swann Perarnau, Pete Beckman *et al*
| In *High-Performance, Power-Aware Computing (HPPAC)*, 2016.
