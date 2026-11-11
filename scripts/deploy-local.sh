#!/usr/bin/env bash
# Construit les images sur le Mac puis les déploie sur le cluster local (Docker Desktop).
# Chaque exécution utilise un tag unique : Kubernetes voit que les images ont changé
# et remplace les pods un par un (mise à jour sans interruption).
set -euo pipefail
cd "$(dirname "$0")/.."

REGISTRY=ghcr.io/leop250
TAG="dev-$(date +%Y%m%d-%H%M%S)"

echo "==> Construction des images (tag ${TAG})"
for service in auth-service tracking-service frontend; do
  docker build -q -t "${REGISTRY}/muscutrack-${service}:${TAG}" "./${service}" >/dev/null
  echo "    ${service}"
done

./scripts/deploy.sh "${TAG}"
echo "==> Application disponible sur http://localhost:8081"
