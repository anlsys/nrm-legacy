{ stdenv, pythonPackages, hwloc}:

pythonPackages.buildPythonPackage {
  name = "nrm";
  src = ./.;
  propagatedBuildInputs = with pythonPackages;[ six numpy tornado pyzmq hwloc];
  buildInputs = with pythonPackages;[ pytest];
  testPhase = '' pytest '';
}
