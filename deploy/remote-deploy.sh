#!/usr/bin/env bash
set -euo pipefail

: "${IMAGE_TAG:?IMAGE_TAG is required}"
: "${IMAGE_OWNER:?IMAGE_OWNER is required}"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
PREVIOUS_FILE="${PREVIOUS_FILE:-.previous_image_tag}"
PREVIOUS_TAG=""

if [[ -f "${PREVIOUS_FILE}" ]]; then
  PREVIOUS_TAG="$(cat "${PREVIOUS_FILE}" || true)"
fi

echo "${IMAGE_TAG}" > "${PREVIOUS_FILE}"
export IMAGE_TAG IMAGE_OWNER

if [[ -n "${GHCR_TOKEN:-}" ]]; then
  echo "${GHCR_TOKEN}" | docker login ghcr.io -u "${GHCR_USER:-github}" --password-stdin
fi

compose() {
  docker compose -f "${COMPOSE_FILE}" "$@"
}

health() {
  compose exec -T backend wget -q -O /dev/null http://127.0.0.1:8080/health
  compose exec -T ai-service python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8001/health', timeout=2).close()"
  compose exec -T frontend wget -q -O /dev/null http://127.0.0.1:3000/health
}

echo "Deploying image tag ${IMAGE_TAG} (previous: ${PREVIOUS_TAG:-none})"
compose pull
compose up -d --wait --wait-timeout 180 --remove-orphans

if health; then
  echo "Deployment succeeded: ${IMAGE_TAG}"
  compose ps
  exit 0
fi

echo "Health checks failed for ${IMAGE_TAG}" >&2
compose logs --tail=100 >&2 || true

if [[ -n "${PREVIOUS_TAG}" && "${PREVIOUS_TAG}" != "${IMAGE_TAG}" ]]; then
  echo "Restoring previous image tag ${PREVIOUS_TAG}" >&2
  export IMAGE_TAG="${PREVIOUS_TAG}"
  echo "${PREVIOUS_TAG}" > "${PREVIOUS_FILE}"
  compose pull
  compose up -d --wait --wait-timeout 180 --remove-orphans
  health || true
  echo "Previous version restored; deployment is marked failed." >&2
else
  echo "No previous tag to restore." >&2
fi

exit 1
