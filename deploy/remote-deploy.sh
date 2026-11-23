#!/usr/bin/env bash
set -euo pipefail

: "${IMAGE_TAG:?IMAGE_TAG is required}"
: "${IMAGE_OWNER:?IMAGE_OWNER is required}"

# Тег приходит из workflow и не должен содержать команды или пробелы.
[[ "${IMAGE_TAG}" =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}$ ]] || {
  echo "Invalid image tag" >&2
  exit 1
}
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
PREVIOUS_FILE="${PREVIOUS_FILE:-.previous_image_tag}"
PREVIOUS_TAG=""

if [[ -f "${PREVIOUS_FILE}" ]]; then
  PREVIOUS_TAG="$(cat "${PREVIOUS_FILE}" || true)"
fi

export IMAGE_TAG IMAGE_OWNER

if [[ -n "${GHCR_TOKEN:-}" ]]; then
  echo "${GHCR_TOKEN}" | docker login ghcr.io -u "${GHCR_USER:-github}" --password-stdin
fi

compose() {
  docker compose -f "${COMPOSE_FILE}" "$@"
}

health() {
  compose exec -T backend wget -q -O /dev/null http://127.0.0.1:8080/health || return 1
  compose exec -T parser-service python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8001/health', timeout=2).close()" || return 1
  compose exec -T frontend wget -q -O /dev/null http://127.0.0.1:3000/health
}

rollback() {
  if [[ -n "${PREVIOUS_TAG}" && "${PREVIOUS_TAG}" != "${IMAGE_TAG}" ]]; then
    echo "Restoring previous image tag ${PREVIOUS_TAG}" >&2
    export IMAGE_TAG="${PREVIOUS_TAG}"
    if compose pull && compose up -d --wait --wait-timeout 180 --remove-orphans && health; then
      echo "Previous version restored; deployment is marked failed." >&2
    else
      echo "CRITICAL: automatic rollback failed; inspect containers and database migrations." >&2
    fi
  else
    echo "No previous tag to restore." >&2
  fi
  exit 1
}

BACKUP_BEFORE_DEPLOY="${BACKUP_BEFORE_DEPLOY:-1}"
if [[ "${BACKUP_BEFORE_DEPLOY}" == "1" ]] && [[ -n "$(compose ps -q db 2>/dev/null || true)" ]]; then
  mkdir -p backups
  backup_file="backups/rehub-$(date -u +%Y%m%dT%H%M%SZ).sql"
  echo "Creating database backup ${backup_file}"
  if ! compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "${backup_file}"; then
    rm -f "${backup_file}"
    echo "Database backup failed; deployment aborted before image change." >&2
    exit 1
  fi
  find backups -name '*.sql' -type f -mtime +7 -delete 2>/dev/null || true
fi

echo "Deploying image tag ${IMAGE_TAG} (previous: ${PREVIOUS_TAG:-none})"
if ! compose pull; then
  echo "Image pull failed; current containers were not changed." >&2
  exit 1
fi

if ! compose up -d --wait --wait-timeout 180 --remove-orphans; then
  echo "Compose startup failed for ${IMAGE_TAG}" >&2
  compose logs --tail=100 >&2 || true
  rollback
fi

if health; then
  # Сохраняем только подтвержденный рабочий тег, после всех проверок.
  printf '%s\n' "${IMAGE_TAG}" > "${PREVIOUS_FILE}.tmp"
  mv "${PREVIOUS_FILE}.tmp" "${PREVIOUS_FILE}"
  echo "Deployment succeeded: ${IMAGE_TAG}"
  compose ps
  exit 0
fi

echo "Health checks failed for ${IMAGE_TAG}" >&2
compose logs --tail=100 >&2 || true
rollback
