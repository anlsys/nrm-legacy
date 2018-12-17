{ argotest ? (builtins.fetchGit {
    url = https://xgitlab.cels.anl.gov/argo/argotest.git;
    ref="refactor-argotk";
    rev="a20358e5b72f267eb8e2a9152e62c9ebbb3b2d4a"; })
}:
(import argotest {
  nrm-src = ./.;
}).test
