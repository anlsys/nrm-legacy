

plim_module.so: plim.c plimimpl.c
	python setup.py  build_ext --inplace

# build_ext: build extension modules
# --inplace: generate modules in the current directory

clean:
	rm -f plim_module.so
	rm -rf build
