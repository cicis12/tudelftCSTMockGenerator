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

use_tunnel=false
tunnel_env=.cloudflared.env
if [[ -z ${CST_DOMAIN:-} ]]; then
  tunnel_default=n
  [[ ! -s $tunnel_env ]] || tunnel_default=y
  tunnel_answer=$tunnel_default
  if [[ -t 0 ]]; then
    while true; do
      read -r -p "Install and set up a Cloudflare Tunnel using Docker? [y/n, default: $tunnel_default] " tunnel_answer || tunnel_answer=n
      tunnel_answer=${tunnel_answer:-$tunnel_default}
      case "$tunnel_answer" in
        y|Y|yes|YES|n|N|no|NO) break ;;
        *) echo 'Please answer yes or no.' ;;
      esac
    done
  else
    echo "Non-interactive deployment: Cloudflare Tunnel choice defaults to $tunnel_default. Run in a terminal for guided setup."
  fi
  case "$tunnel_answer" in
    y|Y|yes|YES)
      use_tunnel=true
      if [[ ! -s $tunnel_env ]]; then
        cat <<'GUIDE'

Cloudflare Tunnel setup (cloudflared will be installed as a Docker container):
  1. Sign in at https://dash.cloudflare.com with a domain managed by Cloudflare.
  2. Open Networking > Tunnels, select Create Tunnel, and name it "cst-studio".
     In the Zero Trust dashboard, look under Networks > Connectors / Tunnels
     and choose the Cloudflared connector type if prompted.
  3. Select Docker in the connector setup. Copy ONLY the tunnel token from the
     command shown after --token, then paste it at the hidden prompt below.
     This script runs the connector for you; leave the dashboard open.

The token will be saved in .cloudflared.env with owner-only permissions.
No inbound router ports are needed; allow outbound traffic on port 7844.
Guide: https://developers.cloudflare.com/tunnel/get-started/
GUIDE
        while true; do
          tunnel_token=
          if ! read -r -s -p 'Tunnel token (blank to cancel tunnel setup): ' tunnel_token; then
            tunnel_token=
          fi
          printf '\n'
          if [[ -z $tunnel_token ]]; then
            use_tunnel=false
            echo 'Tunnel setup cancelled; continuing with local deployment.'
            break
          fi
          if [[ $tunnel_token =~ ^[A-Za-z0-9_+/=-]+$ ]]; then
            (umask 077; printf 'TUNNEL_TOKEN=%s\n' "$tunnel_token" > "$tunnel_env")
            unset tunnel_token
            break
          fi
          echo 'Paste only the token, without quotes or the Docker command.'
        done
      else
        echo 'Reusing the saved tunnel token from .cloudflared.env.'
      fi
      if [[ $use_tunnel == true ]]; then
        chmod 600 "$tunnel_env"
        compose_files+=(-f compose.tunnel.yml)
      fi
      ;;
  esac
else
  echo 'Using Caddy HTTPS with --domain. For guided Cloudflare Tunnel setup, run ./deploy.sh without --domain.'
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
# Stop a previously deployed tunnel before switching to local or Caddy mode.
if [[ $use_tunnel == false && -s $tunnel_env ]]; then
  docker compose -f compose.yml -f compose.tunnel.yml stop cloudflared
fi
docker compose "${compose_files[@]}" up --build --detach --wait --wait-timeout 180
if [[ $use_tunnel == true ]]; then
  cat <<'GUIDE'

  4. In the Cloudflare dashboard, wait for the connector to show Healthy,
     then select Continue. Open the tunnel's Routes / Published applications
     and add a Published application route (also called a Public hostname).
  5. Choose your public hostname, for example cst.example.com.
     Set service type to HTTP and URL to app:8000 (http://app:8000).
     Use app:8000 even if APP_PORT differs; cloudflared runs inside Docker.
     Save the route. Cloudflare manages the hostname's DNS and public HTTPS.
  6. Open https://YOUR_HOSTNAME and check the app and /admin login.
     Secure cookies are enabled: use the public HTTPS URL to sign in.

On redeploy, accept the tunnel prompt to reuse your saved configuration.
Status: docker compose -f compose.yml -f compose.tunnel.yml ps
Logs:   docker compose -f compose.yml -f compose.tunnel.yml logs --tail=100 cloudflared
If the connector is not Healthy, check the logs and outbound port 7844.
To replace the token, remove .cloudflared.env and run ./deploy.sh again.
GUIDE
elif [[ -n ${CST_DOMAIN:-} ]]; then
  echo "CST Studio is ready at https://${CST_DOMAIN} (DNS must point here; ports 80 and 443 must be reachable)."
else
  echo 'CST Studio is ready on localhost at APP_PORT from .env (default: http://localhost:8000).'
fi
echo 'Admin: /admin. Credentials: ADMIN_PASSWORD in .env. Existing database data is retained on redeploy.'
