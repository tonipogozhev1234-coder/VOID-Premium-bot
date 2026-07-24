#!/usr/bin/env bash
# Запуск бота вручную (из папки проекта)
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo "Нет файла .env — скопируй .env.example → .env и заполни."
  exit 1
fi

if [[ ! -d .venv ]]; then
  echo "Создаю venv…"
  python3 -m venv .venv
  .venv/bin/pip install -U pip
  .venv/bin/pip install -r requirements.txt
fi

exec .venv/bin/python bot.py
