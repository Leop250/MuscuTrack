#!/usr/bin/env bash
# Déploie sur le cluster Kubernetes courant les images portant le tag donné.
# Utilisé par scripts/deploy-local.sh (images construites sur le Mac)
# et par le pipeline de release (images publiées sur GHCR).
#   Usage : scripts/deploy.sh <tag>
set -euo pipefail
cd "$(dirname "$0")/.."

TAG="${1:?Usage : scripts/deploy.sh <tag>}"
REGISTRY=ghcr.io/leop250
NAMESPACE=muscutrack
SERVICES=(auth-service tracking-service frontend)

echo "==> Namespace et Secret"
kubectl apply -f deploy/namespace.yaml
if ! kubectl -n "${NAMESPACE}" get secret muscutrack-secrets >/dev/null 2>&1; then
  # Valeurs aléatoires, jamais écrites sur le disque ni dans Git.
  kubectl -n "${NAMESPACE}" create secret generic muscutrack-secrets \
    --from-literal=POSTGRES_PASSWORD="$(openssl rand -hex 24)" \
    --from-literal=JWT_SECRET="$(openssl rand -hex 32)"
fi

echo "==> Application des manifestes (images ${TAG})"
# Remplace le tag "latest" de kustomization.yaml par celui à déployer.
kubectl kustomize deploy/ \
  | sed -E "s#(${REGISTRY}/muscutrack-[a-z-]+):latest#\1:${TAG}#" \
  | kubectl apply -f -

for deployment in postgres "${SERVICES[@]}"; do
  kubectl -n "${NAMESPACE}" rollout status "deployment/${deployment}" --timeout=180s
done

echo "==> Déployé : ${TAG}"
