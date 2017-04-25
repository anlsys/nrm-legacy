"""Argo Node Resource Manager
"""

from setuptools import setup, find_packages

setup(
    name='nrm',
    version='0.0.1',
    description="Argo Node Resource Manager",
    author='Swann Perarnau',
    author_email='swann@anl.gov',
    url='http://argo-osr.org',
    license='MIT',

    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
    ],

    packages=find_packages(),
    install_requires=['six', 'pyzmq', 'tornado'],
    scripts=['bin/daemon', 'bin/client']
)
