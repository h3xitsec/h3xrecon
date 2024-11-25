{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShellNoCC {
  packages = with pkgs; [
    (python3.withPackages (ps: [ 
      ps.ansible
      ps.ansible-core
      ps.asyncpg 
      ps.certifi
      ps.charset-normalizer
      ps.idna
      ps.loguru
      ps.nats-py
      ps.requests
      ps.urllib3
      ps.redis
    ]))
    curl
    nodejs_18
    jq
    ipinfo
    postgresql
    nats-server
    natscli
    libz
    go
    gcc
    nmap
    pv
    dos2unix
    gh
    hatch
    amass
  ];
  shellHook = ''
    export LD_LIBRARY_PATH="/run/current-system/sw/share/nix-ld/lib"
  '';
}


