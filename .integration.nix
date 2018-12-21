{ argotest ? (builtins.fetchGit {
    url = https://xgitlab.cels.anl.gov/argo/argotest.git;
    ref="master";
    rev="646d42f7b64f56cdb3ff54a7b4a59e0dfad3209c";
})
}:
(import argotest {
  nrm-src = ./.;
  libnrm-src = builtins.fetchGit {
      url = https://xgitlab.cels.anl.gov/argo/libnrm.git;
      ref="downstream-refactor"; };
}).test
