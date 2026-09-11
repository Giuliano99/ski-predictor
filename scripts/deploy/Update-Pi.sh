#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="${SKI_PREDICTOR_REPO:-/home/pi/ski-predictor}"
branch="${SKI_PREDICTOR_BRANCH:-main}"

exec 9>"/tmp/ski-predictor-git-update.lock"
if ! flock -n 9; then
  echo "Ein Update laeuft bereits."
  exit 0
fi

if [[ ! -d "$repo_dir/.git" ]]; then
  echo "Repository nicht gefunden: $repo_dir" >&2
  exit 1
fi

cd "$repo_dir"

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "Update abgebrochen: Auf dem Pi liegen nicht eingecheckte Aenderungen." >&2
  exit 1
fi

git fetch --prune origin "$branch"

local_commit="$(git rev-parse HEAD)"
remote_commit="$(git rev-parse "origin/$branch")"

if [[ "$local_commit" == "$remote_commit" ]]; then
  echo "Bereits aktuell: $local_commit"
  exit 0
fi

if ! git merge-base --is-ancestor "$local_commit" "$remote_commit"; then
  echo "Update abgebrochen: origin/$branch ist kein Fast-Forward." >&2
  exit 1
fi

git merge --ff-only "$remote_commit"
echo "Aktualisiert: $local_commit -> $remote_commit"

runtime_root="${SKI_PREDICTOR_RUNTIME:-/srv/ski-predictor}"
if [[ -f "$runtime_root/config/auto-deploy-enabled" ]]; then
  echo "Container werden aktualisiert ..."
  docker compose \
    --env-file "$runtime_root/config/runtime.env" \
    -f compose.pi.yaml \
    up -d --build --remove-orphans
fi
