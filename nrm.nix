{ stdenv, pythonPackages, hwloc, nrm-containers }:

pythonPackages.buildPythonPackage {
  name = "nrm";
  src = ./.;
  propagatedBuildInputs = with pythonPackages;[ six numpy tornado pyzmq hwloc docopt nrm-containers];
  buildInputs = with pythonPackages;[ pytest];
  testPhase = '' pytest '';
}
