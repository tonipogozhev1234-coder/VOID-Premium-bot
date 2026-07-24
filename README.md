# VOID Premium Telegram Bot

Telegram-бот для [VOID](https://webvoid.ru): Premium-подписка за Stars, коды доступа к сайту, вход через Telegram и синхронизация с API сайта.

## Возможности

- Продажа Premium за Telegram Stars (`/buy`)
- 16-символьные коды для активации на сайте
- Привязка Telegram к аккаунту VOID (`/start link_…`)
- Вход на сайт через 6-значный код (`/start login_…`)
- Админ-команды: заморозка, продление, отзыв подписок

## Быстрый старт

```bash
cp .env.example .env
# заполни BOT_TOKEN, BOT_API_SECRET, ADMIN_ID

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python bot.py
```

Или на Linux: `./start.sh`

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN` | Токен от [@BotFather](https://t.me/BotFather) |
| `BOT_API_SECRET` | Общий секрет с `api/config.php` на сайте |
| `ADMIN_ID` | Telegram ID администратора |
| `SITE_API_URL` | URL API сайта (по умолчанию `https://webvoid.ru/api`) |
| `VIP_PRICE_STARS` | Цена Premium в Stars (по умолчанию 100) |

Полный список — в [.env.example](.env.example).

## Деплой на VPS

```bash
sudo bash deploy/install-vps.sh
```

Скрипт установит systemd-сервис `void-bot` в `/opt/void-bot`.

## Docker

```bash
cp .env.example .env
docker compose up -d --build
```

## Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие и статус |
| `/buy` | Купить Premium |
| `/vip` | Статус подписки |
| `/mycode` | Показать код |
| `/newcode` | Перегенерировать код |
| `/help` | Справка |

**Не коммитьте `.env`** — в нём секреты.
