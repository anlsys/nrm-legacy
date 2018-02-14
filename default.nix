{
  pkgs ? import ( fetchTarball "https://github.com/NixOS/nixpkgs/archive/17.09.tar.gz") {},
}:
let
  callPackage = pkgs.lib.callPackageWith (pkgs // pkgs.xlibs // self);
  self = rec {
    # Freeze python version to 3.5
    pythonPackages = pkgs.python27Packages;
    python = pkgs.python27;
    slots = callPackage ./slots.nix { inherit pythonPackages; };
    nrm = callPackage ./nrm.nix { inherit pythonPackages; };
    inherit pkgs;
  };
in
  self
