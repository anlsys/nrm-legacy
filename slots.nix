{ stdenv, pythonPackages, fetchFromGitHub}:

pythonPackages.buildPythonPackage {
  name = "nrm";
  src = fetchFromGitHub {
    owner = "roycoding";
    repo = "slots" ;
    rev = "1ed9b203fa02002c09b9dad73e2a97c04a45ef20";
    sha256 = "0xv76lj9xpfh1jj78n9vxyiyakygn3q83cmvyrv1bwkj10f9x575";
  };

  propagatedBuildInputs = with pythonPackages;[ numpy ];
}
