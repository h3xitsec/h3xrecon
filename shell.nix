{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShellNoCC {
  packages = with pkgs; [
    (python3.withPackages (ps: [ 
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
  ];
  shellHook = ''
    export PGPASSWORD="h3xrecon"
    export H3XRECON_PROCESSOR_IP=100.122.156.98
    export H3XRECON_REDIS_SERVER=$H3XRECON_PROCESSOR_IP
    export H3XRECON_REDIS_PORT=6379
    export H3XRECON_NATS_SERVER=$H3XRECON_PROCESSOR_IP
    export H3XRECON_NATS_PORT=4222
    export H3XRECON_DB_HOST=$H3XRECON_PROCESSOR_IP
    export H3XRECON_DB_PORT=5432
    export H3XRECON_DB_USER=h3xrecon
    export H3XRECON_DB_PASSWORD=h3xrecon
    export H3XRECON_DB_NAME=h3xrecon
    export LOGURU_LEVEL=DEBUG
    export DOCKER_HOST=ssh://recon
    export PATH="./Worker/bin:~/.local/share/go/bin:$PATH"
    export LD_LIBRARY_PATH="/run/current-system/sw/share/nix-ld/lib"
    source ./venv/bin/activate
    python -m pip uninstall -y httpx > /dev/null 2>&1
    go install -v github.com/projectdiscovery/pdtm/cmd/pdtm@latest
    pdtm -s -bp ~/.local/share/go/bin -i httpx > /dev/null 2>&1
  '';
}

