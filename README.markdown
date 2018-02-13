# Argo Node Resource Manager

Resource management daemon using communication with clients to control
power usage of application.

This is a python rewrite of the original code developed for the Argo project
two years ago.

## Additional Info

| **Systemwide Power Management with Argo**
| Dan Ellsworth, Tapasya Patki, Swann Perarnau, Pete Beckman *et al*
| In *High-Performance, Power-Aware Computing (HPPAC)*, 2016.

## Packaging

building:
nix-build -A nrm
