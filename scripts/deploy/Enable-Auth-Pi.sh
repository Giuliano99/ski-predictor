#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="${SKI_PREDICTOR_REPO:-/home/pi/ski-predictor}"
runtime_root="${SKI_PREDICTOR_RUNTIME:-/srv/ski-predictor}"
service_user="${SUDO_USER:-pi}"
environment_file="$runtime_root/config/runtime.env"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Bitte mit sudo ausfuehren: sudo $0" >&2
  exit 1
fi
if [[ ! -f "$environment_file" ]]; then
  echo "Laufzeitkonfiguration fehlt: $environment_file" >&2
  exit 1
fi

read -r -p "Benutzername des Spielleiters [giuliano]: " admin_username
admin_username="${admin_username:-giuliano}"
read -r -p "Anzeigename des Spielleiters [Giuliano]: " admin_display_name
admin_display_name="${admin_display_name:-Giuliano}"

sudo -u "$service_user" docker compose \
  --env-file "$environment_file" \
  -f "$repo_dir/compose.pi.yaml" \
  exec -T app python services/api/src/database_cli.py migrate

sudo -u "$service_user" docker compose \
  --env-file "$environment_file" \
  -f "$repo_dir/compose.pi.yaml" \
  exec app python services/api/src/database_cli.py create-user \
  --username "$admin_username" --display-name "$admin_display_name" --role GAME_MASTER

registration_code="$(openssl rand -hex 6)"
set_environment() {
  local name="$1"
  local value="$2"
  if grep -q "^${name}=" "$environment_file"; then
    sed -i "s|^${name}=.*|${name}=${value}|" "$environment_file"
  else
    printf '%s=%s\n' "$name" "$value" >>"$environment_file"
  fi
}

set_environment SKI_AUTH_REQUIRED 1
set_environment SKI_REGISTRATION_CODE "$registration_code"
set_environment SKI_SECURE_COOKIES 0
chmod 0640 "$environment_file"

sudo -u "$service_user" docker compose \
  --env-file "$environment_file" \
  -f "$repo_dir/compose.pi.yaml" \
  up -d --force-recreate app

echo
echo "Authentifizierung ist aktiviert."
echo "Einladungscode fuer die Testgruppe: $registration_code"
echo "Der Code steht nur in $environment_file und wird nicht in Git gespeichert."
