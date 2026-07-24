# VOID Premium Telegram Bot

Telegram-бот для [VOID](https://webvoid.ru): Premium за Stars, коды доступа, вход через Telegram.

## Bothost.ru (рекомендуется)

Репозиторий **должен быть публичным**, иначе Bothost не сможет его клонировать.

### Создание бота

1. Откройте [bothost.ru/create-bot.php](https://bothost.ru/create-bot.php)
2. Заполните:
   - **Платформа:** Telegram  
   - **Библиотека:** aiogram  
   - **Bot Token:** токен от [@BotFather](https://t.me/BotFather)  
   - **Git URL:** `https://github.com/tonipogozhev1234-coder/VOID-Premium-bot`  
   - **Ветка:** `main`  
   - **Главный файл:** `bot.py` (или оставьте пустым — сработает `main.py`)
3. **Переменные окружения** (кроме `BOT_TOKEN` — его Bothost ставит сам):

| Ключ | Значение |
|------|----------|
| `BOT_API_SECRET` | тот же секрет, что в `api/config.php` на сайте |
| `ADMIN_ID` | ваш Telegram ID (число) |
| `SITE_API_URL` | `https://webvoid.ru/api` |
| `DATA_FILE` | `/app/data/vip_data.json` |

4. **Дополнительные настройки:**
   - можно **не** включать «свой Dockerfile» — Bothost сам подхватит Python + `requirements.txt`
   - если включаете Dockerfile — он уже есть в корне
5. Создайте бота и смотрите **логи runtime**
6. **Остановите локальный бот** на ПК (иначе `Conflict: terminated by other getUpdates request`)

### Если Git «не клонируется»

- Репозиторий приватный → Bothost получит 404. Сделайте его **Public** на GitHub:  
  Settings → General → Danger Zone → Change repository visibility → Public  
- Или используйте публичный URL из этого README.

## Локальный запуск

```bash
cp .env.example .env
# BOT_TOKEN, BOT_API_SECRET, ADMIN_ID

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python bot.py
```

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN` | Токен от BotFather (Bothost: `TELEGRAM_BOT_TOKEN` / `API_TOKEN` тоже ок) |
| `BOT_API_SECRET` | Секрет с сайта (`api/config.php`) — **обязателен** |
| `ADMIN_ID` | Telegram ID админа |
| `SITE_API_URL` | По умолчанию `https://webvoid.ru/api` |
| `VIP_PRICE_STARS` | Цена Premium в Stars (100) |
| `DATA_FILE` | Путь к JSON с VIP-кодами |

## Структура (то, что нужно Bothost)

```
├── bot.py              # основной код
├── main.py             # точка входа (автодетект Bothost)
├── requirements.txt    # aiogram, aiohttp
├── Dockerfile          # опционально
├── .env.example
└── README.md
```

## Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие и статус |
| `/buy` | Купить Premium |
| `/vip` | Статус |
| `/mycode` | Показать код |
| `/newcode` | Новый код |
| `/help` | Справка |

### Секретная выдача Premium (только админ)

Только если `ADMIN_ID` = твой Telegram ID. Обычным юзерам команда молчит.

| Команда | Что делает |
|---------|------------|
| `/voidgift` | себе Premium на 30 дней |
| `/voidgift me 60` | себе на 60 дней |
| `/voidgift 123456789` | юзеру по TG ID |
| `/voidgift 123456789 90` | юзеру на 90 дней |

Имя команды можно сменить: env `GIFT_SECRET_CMD=mysecret` → `/mysecret`.

**Не коммитьте `.env`** — только переменные окружения на Bothost.
