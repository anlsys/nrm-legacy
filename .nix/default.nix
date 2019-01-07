let argotest =
  builtins.fetchTarball
  "https://xgitlab.cels.anl.gov/argo/argotest/-/archive/master/argotest-master.tar.gz";
in import "${argotest}/test.nix" {
  nrm-override = ./..;
  testName = "base";
}
