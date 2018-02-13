{
  pkgs ? import ( fetchTarball "https://github.com/NixOS/nixpkgs/archive/17.09.tar.gz") {},
}:
let
  callPackage = pkgs.lib.callPackageWith (pkgs  //  self);
  pythonPackages = pkgs.python27Packages;
  self = rec {
    nrm = callPackage ./nrm.nix { inherit pythonPackages ; };
    inherit pkgs;
  };
in
  self
