#!/usr/bin/env bash
# Copyright 2024 Chmouel Boudjnah <chmouel@chmouel.com>
set -eufo pipefail
NS=forgejo
fpath=$(dirname "$0")
FORGE_HOST=$(echo -n forgejo."$(kubectl get route -n openshift-console console -o json | jq -r .spec.host | sed 's/.*\.app/app/')")
TMP=$(mktemp /tmp/.mm.XXXXXX)
clean() { rm -f ${TMP}; }
trap clean EXIT

kubectl create namespace ${NS} 2>/dev/null || true
helm uninstall forgejo -n ${NS} 2>/dev/null || true

cat ${fpath}/values.yaml >${TMP}
cat <<EOF >>${TMP}

route:
  enabled: true

global:
  compatibility:
    openshift:
      adaptSecurityContext: force
EOF

helm install forgejo oci://code.forgejo.org/forgejo-helm/forgejo \
  --wait \
  -n ${NS} \
  -f ${TMP} \
  --set ingress.enabled=false \
  --set route.host=${FORGE_HOST} \
  --set gitea.config.server.DOMAIN=${FORGE_HOST} \
  --set gitea.config.server.ROOT_URL=https://${FORGE_HOST} \
  --set gitea.config.server.SSH_DOMAIN=${FORGE_HOST} \
  --create-namespace
