#!/usr/bin/env bash
# Déploie l'application sur le cluster Kubernetes local (Docker Desktop).
# Chaque exécution construit des images avec un tag unique : Kubernetes voit
# qu'elles ont changé et remplace les pods un par un (mise à jour sans interruption).
set -euo pipefail
cd "$(dirname "$0")/.."

REGISTRY=ghcr.io/leop250
NAMESPACE=muscutrack
SERVICES=(auth-service tracking-service frontend)
TAG="dev-$(date +%Y%m%d-%H%M%S)"

echo "==> Construction des images (tag ${TAG})"
for service in "${SERVICES[@]}"; do
  docker build -q -t "${REGISTRY}/muscutrack-${service}:${TAG}" "./${service}" >/dev/null
  echo "    ${service}"
done

echo "==> Namespace et Secret"
kubectl apply -f deploy/namespace.yaml
if ! kubectl -n "${NAMESPACE}" get secret muscutrack-secrets >/dev/null 2>&1; then
  # Valeurs aléatoires, jamais écrites sur le disque ni dans Git.
  kubectl -n "${NAMESPACE}" create secret generic muscutrack-secrets \
    --from-literal=POSTGRES_PASSWORD="$(openssl rand -hex 24)" \
    --from-literal=JWT_SECRET="$(openssl rand -hex 32)"
fi

echo "==> Application des manifestes"
# Remplace le tag "latest" de kustomization.yaml par celui qu'on vient de construire.
kubectl kustomize deploy/ \
  | sed -E "s#(${REGISTRY}/muscutrack-[a-z-]+):latest#\1:${TAG}#" \
  | kubectl apply -f -

for deployment in postgres "${SERVICES[@]}"; do
  kubectl -n "${NAMESPACE}" rollout status "deployment/${deployment}" --timeout=180s
done

echo "==> Application disponible sur http://localhost:8081"
