#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="${SKI_PREDICTOR_REPO:-/home/pi/ski-predictor}"
runtime_root="${SKI_PREDICTOR_RUNTIME:-/srv/ski-predictor}"
service_user="${SUDO_USER:-pi}"
environment_file="$runtime_root/config/runtime.env"
marker_file="$runtime_root/config/public-https-enabled"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Bitte mit sudo ausfuehren: sudo $0" >&2
  exit 1
fi

set_environment() {
  local name="$1"
  local value="$2"
  if grep -q "^${name}=" "$environment_file"; then
    sed -i "s|^${name}=.*|${name}=${value}|" "$environment_file"
  else
    printf '%s=%s\n' "$name" "$value" >>"$environment_file"
  fi
}

set_environment SKI_SECURE_COOKIES 0
set_environment SKI_BIND_ADDRESS 0.0.0.0
rm -f -- "$marker_file"
chmod 0640 "$environment_file"

sudo -u "$service_user" docker compose \
  --env-file "$environment_file" \
  -f "$repo_dir/compose.pi.yaml" \
  up -d --force-recreate --remove-orphans app

echo "Der oeffentliche HTTPS-Testzugang ist deaktiviert."
