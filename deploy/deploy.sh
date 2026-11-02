#!/usr/bin/env sh
# Run on the server from the folder that holds compose.server.yaml and .env.
#   ./deploy.sh                 deploy TAG from .env (default: latest)
#   TAG=sha-1a2b3c4 ./deploy.sh deploy or roll back to a specific build
set -eu
cd "$(dirname "$0")"
[ -f .env ] || { echo "Missing .env (copy .env.example)"; exit 1; }

docker compose -f compose.server.yaml pull
docker compose -f compose.server.yaml up -d
docker compose -f compose.server.yaml ps
docker image prune -f >/dev/null
