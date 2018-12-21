let hostPkgs = import <nixpkgs> {};
in
  {
    nrm        ? ../.,
    argotest   ? (hostPkgs.nix-update-source.fetch pins/argotest.json).src ,
    libnrm     ? (hostPkgs.nix-update-source.fetch pins/libnrm.json).src ,
    containers ? (hostPkgs.nix-update-source.fetch pins/containers.json).src
  }:
  import "${argotest}/default.nix"
  {
    nrm-src        = nrm;
    libnrm-src     = libnrm;
    containers-src = containers;
  }
