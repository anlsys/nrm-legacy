PYTHON:= $(shell which python2)

source:
	$(PYTHON) setup.py sdist

install:
	$(PYTHON) setup.py install --force --prefix /g/g91/ramesh2/ARGO/NRM

check:
	tox
