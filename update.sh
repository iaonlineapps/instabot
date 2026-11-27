#!/usr/bin/env bash
# InstaBot: instala o actualiza el bot en la Raspberry Pi 5.
# Uso:  curl -fsSL https://raw.githubusercontent.com/iaonlineapps/instabot/main/update.sh | bash
set -euo pipefail
REPO="iaonlineapps/instabot"
ARCANE="/var/lib/docker/volumes/arcane_arcane-data/_data/projects"
PUBLIC_URL_DEFAULT="https://insta.familiapm.site"

say() { printf '\n\033[1;36m%s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31m❌ %s\033[0m\n' "$*"; exit 1; }
sudo() { if [ "$(id -u)" = "0" ]; then "$@"; else command sudo "$@"; fi; }

command -v docker >/dev/null || fail "No encuentro Docker en esta máquina."
sudo docker compose version >/dev/null 2>&1 || fail "Falta «docker compose»."

DIR=$(sudo docker inspect instabot --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' 2>/dev/null || true)
if [ -z "$DIR" ]; then
  if sudo test -d "$ARCANE"; then DIR="$ARCANE/instabot"; else DIR="$HOME/instabot"; fi
fi
say "📦 Bajando InstaBot a $DIR"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
curl -fsSL "https://codeload.github.com/$REPO/tar.gz/refs/heads/main" | tar xz -C "$TMP" --strip-components=1
sudo mkdir -p "$DIR/data"
sudo cp -r "$TMP"/. "$DIR"/
sudo touch "$DIR/.env"
sudo chmod 600 "$DIR/.env"

if ! sudo grep -q '^TELEGRAM_TOKEN=..*' "$DIR/.env"; then
  say "🔑 Pega aquí el token que te dio @BotFather y pulsa Enter:"
  while true; do
    read -r TOKEN < /dev/tty
    TOKEN=$(echo "$TOKEN" | tr -d '[:space:]')
    NAME=$(curl -fsS "https://api.telegram.org/bot${TOKEN}/getMe" 2>/dev/null | sed -n 's/.*"username":"\([^"]*\)".*/\1/p' || true)
    [ -n "$NAME" ] && break
    echo "Ese token no vale. Cópialo otra vez de @BotFather (es como 123456789:AA...) y pégalo:"
  done
  echo "Bot encontrado: @$NAME"
  echo "TELEGRAM_TOKEN=$TOKEN" | sudo tee -a "$DIR/.env" >/dev/null
fi
sudo grep -q '^PUBLIC_URL=' "$DIR/.env" || echo "PUBLIC_URL=$PUBLIC_URL_DEFAULT" | sudo tee -a "$DIR/.env" >/dev/null

say "🐳 Arrancando el bot (la primera vez tarda unos minutos)"
cd "$DIR"
sudo docker compose up -d --build --remove-orphans

for i in $(seq 1 30); do
  curl -fsS http://127.0.0.1:8097/salud >/dev/null 2>&1 && break
  sleep 2
done
VER=$(sed -n 's/^VERSION = "\(.*\)"/\1/p' "$DIR/bot/main.py")
if curl -fsS http://127.0.0.1:8097/salud >/dev/null 2>&1; then
  TOKEN=$(sudo sed -n 's/^TELEGRAM_TOKEN=//p' "$DIR/.env")
  NAME=$(curl -fsS "https://api.telegram.org/bot${TOKEN}/getMe" 2>/dev/null | sed -n 's/.*"username":"\([^"]*\)".*/\1/p' || true)
  say "✅ InstaBot $VER funcionando."
  echo "Abre tu bot en Telegram (@${NAME:-tu_bot}) y escríbele /start"
else
  sudo docker logs --tail 30 instabot || true
  fail "El bot no arranca. Copia lo de arriba y pásaselo a Claude."
fi
