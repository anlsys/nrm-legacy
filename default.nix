{
  pkgs ? import <argopkgs> {nrm-src=./.;},
}:
rec {
  nrm = pkgs.nrm;
  hack = nrm.overrideAttrs (old:{
    buildInputs = old.buildInputs ++ [pkgs.pythonPackages.flake8];
  });
}
