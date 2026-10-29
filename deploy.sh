#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  echo 'Install Docker Engine or Docker Desktop with Docker Compose v2, then run this script again.' >&2
  exit 1
fi
command -v openssl >/dev/null || { echo 'OpenSSL is required to generate deployment secrets.' >&2; exit 1; }
compose_files=(-f compose.yml)
if [[ ${1:-} == '--domain' && -n ${2:-} && $# == 2 ]]; then
  [[ $2 =~ ^[A-Za-z0-9][A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] || { echo 'Provide a valid public hostname without a URL scheme.' >&2; exit 1; }
  export CST_DOMAIN="$2"
  compose_files+=(-f compose.https.yml)
elif [[ $# != 0 ]]; then
  echo 'Usage: ./deploy.sh [--domain cst.example.com]' >&2
  exit 1
fi
if [[ ! -f .env ]]; then
  umask 077
  cat > .env <<ENV
SECRET_KEY=$(openssl rand -hex 32)
ADMIN_PASSWORD=$(openssl rand -hex 18)
POSTGRES_PASSWORD=$(openssl rand -hex 24)
APP_PORT=8000
COOKIE_SECURE=false
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
MATH_QUESTION_COUNT=24
LOGIC_QUESTION_COUNT=20
CORRECT_ANSWER_COOLDOWN_DAYS=7
ENV
  echo 'Created .env with random secrets. Find your admin password in that file.'
fi
chmod 600 .env
docker compose "${compose_files[@]}" up --build --detach --wait --wait-timeout 180
if [[ -n ${CST_DOMAIN:-} ]]; then
  echo "CST Studio is ready at https://${CST_DOMAIN} (DNS must point here; ports 80 and 443 must be reachable)."
else
  echo 'CST Studio is ready on localhost at APP_PORT from .env (default: http://localhost:8000).'
fi
echo 'Admin: /admin. Credentials: ADMIN_PASSWORD in .env. Existing database data is retained on redeploy.'
