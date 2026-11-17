#!/usr/bin/env bash
set -euo pipefail

: "${IMAGE_TAG:?IMAGE_TAG is required}"
: "${IMAGE_OWNER:?IMAGE_OWNER is required}"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
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

echo "Rolling back to ${IMAGE_TAG}"
compose pull
compose up -d --wait --wait-timeout 180 --remove-orphans

if health; then
  echo "${IMAGE_TAG}" > .previous_image_tag
  echo "Rollback succeeded: ${IMAGE_TAG}"
  compose ps
  exit 0
fi

echo "Rollback health checks failed for ${IMAGE_TAG}" >&2
compose logs --tail=100 >&2 || true
exit 1
