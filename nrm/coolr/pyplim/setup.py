from distutils.core import setup, Extension

plim_module = Extension('plim_module', include_dirs=['./'], sources=['plim.c', 'plimimpl.c'])

# https://docs.python.org/2/distutils/apiref.html
# define_macros, include_dirs, libraries, library_dirs
# extra_compile_args = ["-O2", "-Wall"]

setup(ext_modules=[plim_module])

