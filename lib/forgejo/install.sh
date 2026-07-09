#!/usr/bin/env bash
# Copyright 2024 Chmouel Boudjnah <chmouel@chmouel.com>
set -eufo pipefail
NS=forgejo
fpath=$(dirname "$0")
# shellcheck disable=SC1091
source "${fpath}"/../common.sh
[[ -n ${1:-""} ]] && FORGE_HOST=${1}
FORGE_HOST=${FORGE_HOST:-""}
[[ -z ${FORGE_HOST} ]] && { echo "You need to specify a FORGE_HOST" && exit 1; }

kubectl create namespace ${NS} 2>/dev/null || true

helm uninstall forgejo -n ${NS} >/dev/null 2>&1 || true
helm install --wait -f ${fpath}/values.yaml \
  --replace \
  --version 15.1.0 \
  --set gitea.config.server.DOMAIN=${FORGE_HOST} \
  --set gitea.config.server.ROOT_URL=https://${FORGE_HOST} \
  --set gitea.config.server.SSH_DOMAIN=${FORGE_HOST} \
  --create-namespace -n ${NS} forgejo oci://code.forgejo.org/forgejo-helm/forgejo

# Route Forgejo via the shared Envoy Gateway
create_httproute ${NS} forgejo-http ${FORGE_HOST} 3000
