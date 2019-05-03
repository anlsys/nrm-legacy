#include <Python.h>
#include <stdint.h>

extern uint64_t set_power_limit(int pkgid, double watt);

static PyObject *plim(PyObject *self, PyObject *args)
{
	int pkgid;
	double watt;

	if (!PyArg_ParseTuple(args, "id", &pkgid,  &watt)) {
		return NULL;
	}

	set_power_limit(pkgid, watt);

	// return Py_BuildValue("f", out);
	Py_RETURN_NONE;
}

static PyMethodDef PlimMethods[] = {
	{"plim", plim, METH_VARARGS, "arg1=pkgid, args2=watt"},
	{NULL, NULL, 0, NULL}
};

#if PY_MAJOR_VERSION >= 3
static struct PyModuleDef cModPyDem = {
	PyModuleDef_HEAD_INIT,
	"plim_module", "plim module", -1, PlimMethods
};

PyMODINIT_FUNC PyInit_plim_module(void)
{
	return PyModule_Create(&cModPyDem);
}
#else
PyMODINIT_FUNC
initplim_module(void)  // there no other char between 'init' and the module name. init_plim_module would not work
{
	Py_InitModule("plim_module", PlimMethods);
}

#endif
