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

## Деплой на Bothost.ru

1. Репозиторий должен быть на GitHub (публичный или с доступом Bothost):
   `https://github.com/tonipogozhev1234-coder/VOID-Premium-tg-bot`
2. Откройте [bothost.ru/create-bot.php](https://bothost.ru/create-bot.php):
   - **Платформа:** Telegram
   - **Библиотека:** aiogram
   - **Git URL:** ссылка на репозиторий выше
   - **Ветка:** `main`
   - **Главный файл:** `bot.py`
3. В **Переменные окружения** добавьте (кроме BOT_TOKEN из формы):

| Ключ | Значение |
|------|----------|
| `BOT_API_SECRET` | тот же секрет, что в `api/config.php` на сайте |
| `ADMIN_ID` | ваш Telegram ID |
| `SITE_API_URL` | `https://webvoid.ru/api` |
| `DATA_FILE` | `/app/data/vip_data.json` |

4. **Дополнительные настройки:** включите «Использовать собственный Dockerfile» (в репозитории уже есть `Dockerfile`).
5. Нажмите «Создать бота» и смотрите логи в панели.
6. **Остановите локальный бот** на ПК — иначе будет ошибка `Conflict: terminated by other getUpdates request`.

Если бот падает сразу при старте — в логах часто «Не задана переменная BOT_API_SECRET»: добавьте её в переменные окружения Bothost.

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
