#!/usr/bin/env bash
# Установка VOID-бота на Ubuntu/Debian VPS (REG.RU и др.)
# Запуск:  sudo bash deploy/install-vps.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/void-bot}"
APP_USER="${APP_USER:-voidbot}"
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Запусти от root: sudo bash deploy/install-vps.sh"
  exit 1
fi

echo "==> Пользователь ${APP_USER}"
if ! id "${APP_USER}" &>/dev/null; then
  useradd --system --home "${APP_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
fi

echo "==> Python"
apt-get update -y
apt-get install -y python3 python3-venv python3-pip

echo "==> Копирование в ${APP_DIR}"
mkdir -p "${APP_DIR}"
rsync -a --delete \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.idea' \
  --exclude '.git' \
  "${SRC_DIR}/" "${APP_DIR}/"

if [[ ! -f "${APP_DIR}/.env" ]]; then
  if [[ -f "${APP_DIR}/.env.example" ]]; then
    cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
    echo "!! Создан ${APP_DIR}/.env — ОБЯЗАТЕЛЬНО заполни BOT_TOKEN и BOT_API_SECRET"
  fi
fi

echo "==> venv + зависимости"
python3 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/pip" install -U pip
"${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"
chmod 600 "${APP_DIR}/.env" 2>/dev/null || true

echo "==> systemd"
cp "${APP_DIR}/void-bot.service" /etc/systemd/system/void-bot.service
# подставим user/dir если меняли
sed -i "s|User=voidbot|User=${APP_USER}|g" /etc/systemd/system/void-bot.service
sed -i "s|Group=voidbot|Group=${APP_USER}|g" /etc/systemd/system/void-bot.service
sed -i "s|/opt/void-bot|${APP_DIR}|g" /etc/systemd/system/void-bot.service

systemctl daemon-reload
systemctl enable void-bot
systemctl restart void-bot
systemctl --no-pager status void-bot || true

echo ""
echo "Готово. Команды:"
echo "  sudo systemctl status void-bot"
echo "  sudo journalctl -u void-bot -f"
echo "  sudo systemctl restart void-bot"
echo ""
echo "Проверь .env: ${APP_DIR}/.env"
echo "На сайте api/config.php: TELEGRAM_BOT_USERNAME + BOT_API_SECRET"
