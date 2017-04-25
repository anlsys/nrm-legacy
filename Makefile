PYTHON:= $(shell which python2)

source:
	$(PYTHON) setup.py sdist

install:
	$(PYTHON) setup.py install --force

check:
	tox
