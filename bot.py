from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import string
import sys
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import LabeledPrice, PreCheckoutQuery

# ---------------------------------------------------------------------------
# Конфиг из .env (для хостинга / VPS). Секреты НЕ хранить в коде.
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    """Простой загрузчик .env без обязательной зависимости python-dotenv."""
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str | None = None) -> str:
    val = os.environ.get(name, default)
    if val is None or str(val).strip() == "":
        if default is not None:
            return default
        raise SystemExit(
            f"Не задана переменная окружения {name}. "
            f"Скопируй .env.example → .env и заполни значения."
        )
    return str(val).strip()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        return default


# Bothost / хостинги: BOT_TOKEN, TELEGRAM_BOT_TOKEN или API_TOKEN
def _resolve_bot_token() -> str:
    for name in ("BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "API_TOKEN"):
        val = os.environ.get(name, "").strip()
        if val:
            return val
    raise SystemExit(
        "Не задан токен бота. Укажи BOT_TOKEN (Bothost подставляет его из формы) "
        "или TELEGRAM_BOT_TOKEN / API_TOKEN."
    )


BOT_TOKEN = _resolve_bot_token()
ADMIN_ID = _env_int("ADMIN_ID", 0)
VIP_PRICE_STARS = _env_int("VIP_PRICE_STARS", 100)
CODE_LENGTH = _env_int("CODE_LENGTH", 16)
SUBSCRIPTION_DAYS = _env_int("SUBSCRIPTION_DAYS", 30)
OUTBOX_POLL_SEC = max(1, _env_int("OUTBOX_POLL_SEC", 2))

# URL API сайта (без слэша в конце). Пример: https://webvoid.ru/api
SITE_API_URL = _env("SITE_API_URL", "https://webvoid.ru/api").rstrip("/")
# Пароль бот→сайт. НЕ токен Telegram! = BOT_API_SECRET в api/config.php
# На Bothost добавь эту переменную вручную в «Переменные окружения»
BOT_API_SECRET = _env("BOT_API_SECRET")

# deep-link: t.me/bot?start=link_<token> | login_<sessionId>
_LINK_PAYLOAD = re.compile(r"^link_(?P<token>[A-Za-z0-9_-]{8,64})$")
_LOGIN_PAYLOAD = re.compile(r"^login_(?P<session>[A-Za-z0-9_-]{8,64})$")

_data_env = os.environ.get("DATA_FILE", "").strip()
if _data_env:
    DATA_FILE = Path(_data_env)
else:
    # Docker: /app/data/vip_data.json если есть каталог data
    _data_dir = BASE_DIR / "data"
    if _data_dir.is_dir():
        DATA_FILE = _data_dir / "vip_data.json"
    else:
        DATA_FILE = BASE_DIR / "vip_data.json"
CODE_ALPHABET = string.ascii_uppercase + string.digits

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("void-bot")

if ADMIN_ID <= 0:
    logger.warning("ADMIN_ID не задан — админ-команды будут недоступны")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

vip_users: dict[int, dict] = {}
used_codes: set[str] = set()


def load_data():
    global vip_users, used_codes
    if not DATA_FILE.exists():
        return
    try:
        raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as err:
        logger.warning("Не удалось прочитать %s: %s", DATA_FILE, err)
        return

    vip_users = {}
    used_codes = set()
    for uid, item in (raw.get("users") or {}).items():
        try:
            user_id = int(uid)
        except ValueError:
            continue
        expiry_raw = item.get("expiry")
        expiry = datetime.fromisoformat(expiry_raw) if expiry_raw else datetime.now()
        code = str(item.get("code", "")).upper()
        vip_users[user_id] = {
            "expiry": expiry,
            "code": code,
            "frozen": bool(item.get("frozen", False)),
            "username": item.get("username", ""),
        }
        if code:
            used_codes.add(code)


def save_data():
    payload = {
        "users": {
            str(uid): {
                "code": data["code"],
                "expiry": data["expiry"].isoformat(),
                "frozen": data.get("frozen", False),
                "username": data.get("username", ""),
            }
            for uid, data in vip_users.items()
        }
    }
    DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def generate_unique_code() -> str:
    while True:
        code = "".join(random.choices(CODE_ALPHABET, k=CODE_LENGTH))
        if code not in used_codes:
            used_codes.add(code)
            return code


def is_vip_active(user_id: int) -> bool:
    data = vip_users.get(user_id)
    if not data:
        return False
    if data.get("frozen"):
        return False
    return data["expiry"] > datetime.now()


def format_expiry(expiry: datetime) -> str:
    return expiry.strftime("%d.%m.%Y %H:%M")


async def site_post(path: str, **payload) -> dict:
    """POST к API сайта с X-Bot-Secret (или без секрета для публичных — не используем)."""
    url = f"{SITE_API_URL.rstrip('/')}/{path.lstrip('/')}"
    headers = {
        "Content-Type": "application/json",
        "X-Bot-Secret": BOT_API_SECRET,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=15) as resp:
                data = await resp.json(content_type=None)
                if not isinstance(data, dict):
                    data = {"error": str(data)}
                if resp.status >= 400:
                    raise RuntimeError(data.get("error", f"HTTP {resp.status}"))
                return data
    except aiohttp.ClientError as err:
        raise RuntimeError(f"Сайт недоступен: {err}") from err


async def site_api(action: str, **payload) -> dict:
    return await site_post("bot/subscription", action=action, **payload)


async def complete_telegram_link(token: str, telegram_id: int, telegram_username: str) -> dict:
    return await site_post(
        "bot/telegram/complete-link",
        token=token,
        telegramId=telegram_id,
        telegramUsername=telegram_username or "",
    )


async def request_login_code(session_id: str, telegram_id: int, telegram_username: str) -> dict:
    """Сайт находит аккаунт по telegramId и кладёт 6-значный код (в outbox или сразу)."""
    return await site_post(
        "bot/telegram/login-code",
        sessionId=session_id,
        telegramId=telegram_id,
        telegramUsername=telegram_username or "",
    )


async def pull_telegram_outbox() -> list:
    data = await site_post("bot/outbox/pull")
    messages = data.get("messages") or []
    return messages if isinstance(messages, list) else []


async def register_code_on_site(user_id: int, code: str, username: str, days: int = SUBSCRIPTION_DAYS):
    """Регистрирует код на сайте. Бросает RuntimeError при ошибке."""
    return await site_api(
        "register",
        code=code,
        telegramId=user_id,
        telegramUsername=username or "",
        days=days,
    )


async def manage_on_site(action: str, code: str = "", telegram_id: int = 0, days: int = SUBSCRIPTION_DAYS, **extra) -> dict:
    payload = {"code": code, "telegramId": telegram_id, "days": days, **extra}
    return await site_api(action, **payload)


async def regenerate_code_on_site(user_id: int, old_code: str, new_code: str, username: str = "") -> dict:
    """Атомарно меняет код на сайте. Если action regenerate нет — fallback register+revoke."""
    try:
        return await site_api(
            "regenerate",
            code=old_code,
            newCode=new_code,
            telegramId=user_id,
            telegramUsername=username or "",
        )
    except RuntimeError as err:
        err_text = str(err).lower()
        # Старый API без regenerate — делаем вручную
        if "неизвестн" in err_text or "unknown" in err_text:
            await register_code_on_site(user_id, new_code, username)
            if old_code:
                try:
                    await manage_on_site("revoke", code=old_code)
                except RuntimeError as rev_err:
                    logger.warning("Не удалось отозвать старый код %s: %s", old_code, rev_err)
            return {"ok": True, "code": new_code, "status": "pending"}
        raise


def vip_status_text(user_id: int) -> str:
    data = vip_users.get(user_id)
    if not data:
        return "❌ Не активен"
    if data.get("frozen"):
        return "🧊 Заморожен"
    if data["expiry"] <= datetime.now():
        return "⌛ Истёк"
    days = (data["expiry"] - datetime.now()).days
    return f"✅ Активен (осталось {days} дн.)"


@dp.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject):
    user_id = message.from_user.id
    name = message.from_user.first_name
    username = message.from_user.username or ""
    args = (command.args or "").strip()

    # Привязка: /start link_<token>
    # Вход: /start login_<sessionId> → сайт шлёт 6-значный код в этот чат
    if args:
        link_match = _LINK_PAYLOAD.match(args)
        if link_match:
            token = link_match.group("token")
            try:
                result = await complete_telegram_link(token, user_id, username)
            except RuntimeError as err:
                await message.answer(f"❌ Не удалось привязать Telegram:\n{err}")
                return
            uname = result.get("username") or "аккаунт"
            nick = result.get("nickname") or ""
            label = f"{nick} (@{uname})" if nick else f"@{uname}"
            await message.answer(
                f"✅ <b>Telegram привязан к VOID</b>\n\n"
                f"Аккаунт: <b>{label}</b>\n\n"
                f"На сайте: <b>«Войти через Telegram»</b> — "
                f"откройте бота, код придёт сюда (username не нужен).",
                parse_mode="HTML",
            )
            return

        login_match = _LOGIN_PAYLOAD.match(args)
        if login_match:
            session_id = login_match.group("session")
            try:
                result = await request_login_code(session_id, user_id, username)
            except RuntimeError as err:
                await message.answer(f"❌ {err}")
                return
            if result.get("cooldown"):
                wait = result.get("waitSec") or 60
                await message.answer(
                    f"⏳ Код уже отправлен. Подождите ~{wait} сек. "
                    f"или введите его на сайте."
                )
                return
            # Код уходит сообщением с сайта (outbox) или уже в ответе API через deliver.
            # Дополнительно подтвердим в чате:
            nick = result.get("nickname") or result.get("username") or ""
            extra = f"\nАккаунт: <b>{nick}</b>" if nick else ""
            await message.answer(
                f"🔐 <b>Вход на VOID</b>{extra}\n\n"
                f"6-значный код отправлен в этот чат "
                f"(или уже выше).\n"
                f"Введите его на сайте — username не нужен.",
                parse_mode="HTML",
            )
            return

        await message.answer(
            "Неизвестная ссылка запуска.\n\n"
            "• Привязка: Настройки → Безопасность на сайте\n"
            "• Вход: кнопка «Войти через Telegram» на сайте",
            parse_mode="HTML",
        )
        return

    status = vip_status_text(user_id)
    code_info = ""
    if user_id in vip_users and vip_users[user_id]["code"]:
        code_info = f"\n🔑 Ваш код: <code>{vip_users[user_id]['code']}</code>"

    await message.answer(
        f"👋 Привет, {name}!\n\n"
        f"💎 Premium: {status}{code_info}\n\n"
        f"🔐 <b>Вход на сайт</b>\n"
        f"1. Один раз: Настройки → Безопасность → Привязать Telegram\n"
        f"2. «Войти через Telegram» на сайте → код придёт сюда\n"
        f"(username вводить не нужно)\n\n"
        f"/buy — купить Premium\n"
        f"/vip — статус\n"
        f"/mycode — показать код\n"
        f"/newcode — перегенерировать код\n"
        f"/what — что входит в Premium\n"
        f"/help — помощь",
        parse_mode="HTML",
    )


@dp.message(Command("what"))
async def cmd_what(message: types.Message):
    await message.answer(
        "👑 <b>ЧТО ВХОДИТ В Premium (30 ДНЕЙ)</b>\n\n"
        "✨ Полный доступ на сайте\n"
        "🔑 Уникальный 16-символьный код\n"
        "✓ Галочка в профиле на сайте\n"
        "🛡 Поддержка через бота\n"
        "🧊 Управление подпиской: заморозка, продление\n\n"
        f"💰 Цена: {VIP_PRICE_STARS} ⭐\n"
        "⏱ Срок: 30 дней\n\n"
        "Купить: /buy",
        parse_mode="HTML",
    )


@dp.message(Command("buy"))
async def cmd_buy(message: types.Message):
    user_id = message.from_user.id
    if is_vip_active(user_id):
        days = (vip_users[user_id]["expiry"] - datetime.now()).days
        await message.answer(f"⚠️ Premium активен ещё {days} дн.")
        return

    link = await bot.create_invoice_link(
        title="Premium на 1 месяц",
        description="VOID Premium: 16-символьный код для сайта",
        payload=f"vip_{user_id}",
        currency="XTR",
        prices=[LabeledPrice(label="Premium 30 дней", amount=VIP_PRICE_STARS)],
    )

    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[[types.InlineKeyboardButton(text=f"💎 Оплатить {VIP_PRICE_STARS} ⭐", url=link)]]
    )

    await message.answer(
        f"🛒 <b>Premium НА 1 МЕСЯЦ</b>\n\n"
        f"🔑 16-символьный код для сайта VOID\n"
        f"✓ Premium-статус в профиле\n"
        f"🧊 Управление подпиской через бота\n\n"
        f"💰 Цена: {VIP_PRICE_STARS} ⭐\n"
        f"⏱ Срок: 30 дней\n\n"
        f"Подробнее: /what\n\n"
        f"👇 Оплатить:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@dp.message(Command("vip"))
async def cmd_vip(message: types.Message):
    user_id = message.from_user.id
    data = vip_users.get(user_id)
    if not data:
        await message.answer("❌ Premium не активен\n\nКупить: /buy")
        return

    expiry = data["expiry"]
    code = data["code"]
    if data.get("frozen"):
        status = "🧊 Заморожен"
    elif expiry <= datetime.now():
        status = "⌛ Истёк"
    else:
        days = (expiry - datetime.now()).days
        hours = int((expiry - datetime.now()).seconds / 3600)
        status = f"✅ Активен\n⏳ Осталось: {days} дн. {hours} ч."

    await message.answer(
        f"💎 <b>Premium</b>\n\n"
        f"Статус: {status}\n"
        f"🔑 Код: <code>{code}</code>\n"
        f"📅 До: {format_expiry(expiry)}\n\n"
        f"Введи код на сайте: Настройки → VOID Premium",
        parse_mode="HTML",
    )


@dp.message(Command("mycode"))
async def cmd_mycode(message: types.Message):
    user_id = message.from_user.id
    data = vip_users.get(user_id)
    if not data or not data.get("code"):
        await message.answer("❌ У вас нет кода\nКупить: /buy")
        return

    await message.answer(
        f"🔑 <b>ВАШ КОД ДЛЯ САЙТА</b>\n\n"
        f"<code>{data['code']}</code>\n\n"
        f"📅 Действует до: {format_expiry(data['expiry'])}\n\n"
        f"Вставьте код в Настройки → VOID Premium на сайте VOID.\n"
        f"Если код не подходит: /newcode",
        parse_mode="HTML",
    )


@dp.message(Command("newcode", "regenerate"))
async def cmd_newcode(message: types.Message):
    """Перегенерировать 16-символьный код (старый перестаёт работать)."""
    user_id = message.from_user.id
    username = message.from_user.username or ""
    data = vip_users.get(user_id)

    if not data or not data.get("code"):
        await message.answer("❌ У вас нет кода\nКупить: /buy")
        return
    if data.get("frozen"):
        await message.answer("🧊 Подписка заморожена. Сначала разморозьте её.")
        return
    if data["expiry"] <= datetime.now():
        await message.answer("⌛ Подписка истекла. Купите заново: /buy")
        return

    old_code = data["code"]
    # Старый код освобождаем из used_codes, чтобы алфавит не засорялся
    used_codes.discard(old_code)
    new_code = generate_unique_code()

    try:
        await regenerate_code_on_site(user_id, old_code, new_code, username)
    except RuntimeError as err:
        # Вернём старый код в used_codes, откатим new
        used_codes.discard(new_code)
        used_codes.add(old_code)
        await message.answer(
            f"❌ Не удалось перегенерировать код на сайте:\n{err}\n\n"
            f"Старый код всё ещё: <code>{old_code}</code>",
            parse_mode="HTML",
        )
        return

    data["code"] = new_code
    data["username"] = username
    save_data()

    await message.answer(
        f"🔄 <b>КОД ОБНОВЛЁН</b>\n\n"
        f"❌ Старый код больше не действует\n"
        f"✅ Новый: <code>{new_code}</code>\n\n"
        f"📅 До: {format_expiry(data['expiry'])}\n\n"
        f"Введите новый код на сайте:\n"
        f"<b>Настройки → VOID Premium</b>",
        parse_mode="HTML",
    )

    if user_id != ADMIN_ID:
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🔄 Перегенерация кода\n"
                f"👤 @{username or 'юзер'} (ID: {user_id})\n"
                f"Старый: <code>{old_code}</code>\n"
                f"Новый: <code>{new_code}</code>",
                parse_mode="HTML",
            )
        except Exception:
            pass


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    text = (
        "📚 <b>ПОМОЩЬ</b>\n\n"
        "<b>Вход через Telegram:</b>\n"
        "1. Один раз: Настройки → Безопасность → Привязать\n"
        "2. На сайте: «Войти через Telegram»\n"
        "3. Открыть бота — 6-значный код придёт сюда\n"
        "(username на сайте не нужен)\n\n"
        "<b>Premium:</b>\n"
        "1. /buy — оплатить VIP\n"
        "2. Получить 16-символьный код\n"
        "3. Настройки → VOID Premium → ввести код\n\n"
        "<b>Команды:</b>\n"
        "/buy — купить VIP\n"
        "/vip — статус\n"
        "/mycode — показать код\n"
        "/newcode — перегенерировать код\n"
        "/what — что входит\n"
        "/help — помощь"
    )
    if message.from_user.id == ADMIN_ID:
        text += (
            "\n\n<b>Админ:</b>\n"
            "/freeze [код] — заморозить\n"
            "/unfreeze [код] — разморозить\n"
            "/revoke [код] — отозвать\n"
            "/extend [код] [дни] — продлить\n"
            "/sub [код] — инфо о коде"
        )
    await message.answer(text, parse_mode="HTML")


@dp.message(Command("freeze"))
async def cmd_freeze(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    code = (message.text or "").split(maxsplit=1)[1].strip().upper() if len((message.text or "").split()) > 1 else ""
    if not code:
        await message.answer("Использование: /freeze КОД16СИМВОЛОВ")
        return
    try:
        result = await manage_on_site("freeze", code=code)
        for uid, data in vip_users.items():
            if data.get("code") == code:
                data["frozen"] = True
                save_data()
                break
        await message.answer(f"🧊 Код <code>{code}</code> заморожен", parse_mode="HTML")
        logger.info("Freeze result: %s", result)
    except RuntimeError as err:
        await message.answer(f"❌ {err}")


@dp.message(Command("unfreeze"))
async def cmd_unfreeze(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    code = (message.text or "").split(maxsplit=1)[1].strip().upper() if len((message.text or "").split()) > 1 else ""
    if not code:
        await message.answer("Использование: /unfreeze КОД16СИМВОЛОВ")
        return
    try:
        result = await manage_on_site("unfreeze", code=code)
        for uid, data in vip_users.items():
            if data.get("code") == code:
                data["frozen"] = False
                if result.get("expiry"):
                    data["expiry"] = datetime.fromtimestamp(result["expiry"] / 1000)
                save_data()
                break
        await message.answer(f"✅ Код <code>{code}</code> разморожен", parse_mode="HTML")
    except RuntimeError as err:
        await message.answer(f"❌ {err}")


@dp.message(Command("revoke"))
async def cmd_revoke(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    code = (message.text or "").split(maxsplit=1)[1].strip().upper() if len((message.text or "").split()) > 1 else ""
    if not code:
        await message.answer("Использование: /revoke КОД16СИМВОЛОВ")
        return
    try:
        await manage_on_site("revoke", code=code)
        for uid, data in list(vip_users.items()):
            if data.get("code") == code:
                data["frozen"] = False
                data["expiry"] = datetime.now()
                save_data()
                break
        await message.answer(f"⛔ Код <code>{code}</code> отозван", parse_mode="HTML")
    except RuntimeError as err:
        await message.answer(f"❌ {err}")


@dp.message(Command("extend"))
async def cmd_extend(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /extend КОД16СИМВОЛОВ [дни]")
        return
    code = parts[1].strip().upper()
    days = int(parts[2]) if len(parts) > 2 else SUBSCRIPTION_DAYS
    try:
        result = await manage_on_site("extend", code=code, days=days)
        for uid, data in vip_users.items():
            if data.get("code") == code:
                if result.get("expiry"):
                    data["expiry"] = datetime.fromtimestamp(result["expiry"] / 1000)
                save_data()
                break
        await message.answer(f"📅 Код <code>{code}</code> продлён на {days} дн.", parse_mode="HTML")
    except (RuntimeError, ValueError) as err:
        await message.answer(f"❌ {err}")


@dp.message(Command("sub"))
async def cmd_sub(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    code = (message.text or "").split(maxsplit=1)[1].strip().upper() if len((message.text or "").split()) > 1 else ""
    if not code:
        await message.answer("Использование: /sub КОД16СИМВОЛОВ")
        return
    try:
        result = await manage_on_site("info", code=code)
        sub = result.get("subscription", {})
        await message.answer(
            f"📋 <b>Код:</b> <code>{code}</code>\n"
            f"Статус: {sub.get('status', '—')}\n"
            f"TG ID: {sub.get('telegramId', '—')}\n"
            f"Аккаунт: {sub.get('activatedBy') or 'не активирован'}\n"
            f"До: {sub.get('expiry', '—')}",
            parse_mode="HTML",
        )
    except RuntimeError as err:
        await message.answer(f"❌ {err}")


@dp.pre_checkout_query()
async def pre_checkout(pre_checkout: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout.id, ok=True)


@dp.message(lambda m: m.successful_payment is not None)
async def success_payment(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""

    existing = vip_users.get(user_id)
    site_sync_ok = True
    site_sync_error = ""

    if existing and existing.get("code"):
        vip_code = existing["code"]
        base = existing["expiry"] if existing["expiry"] > datetime.now() else datetime.now()
        expiry = base + timedelta(days=SUBSCRIPTION_DAYS)
        try:
            result = await manage_on_site("extend", code=vip_code, days=SUBSCRIPTION_DAYS)
            if result.get("expiry"):
                expiry = datetime.fromtimestamp(result["expiry"] / 1000)
        except RuntimeError as err:
            logger.warning("extend на сайте не удался, пробуем register: %s", err)
            try:
                await register_code_on_site(user_id, vip_code, username)
            except RuntimeError as reg_err:
                site_sync_ok = False
                site_sync_error = str(reg_err)
    else:
        vip_code = generate_unique_code()
        expiry = datetime.now() + timedelta(days=SUBSCRIPTION_DAYS)
        try:
            await register_code_on_site(user_id, vip_code, username)
        except RuntimeError as err:
            site_sync_ok = False
            site_sync_error = str(err)

    vip_users[user_id] = {
        "expiry": expiry,
        "code": vip_code,
        "frozen": False,
        "username": username,
    }
    save_data()

    sync_note = ""
    if not site_sync_ok:
        sync_note = (
            f"\n\n⚠️ <b>Код создан, но сайт его не принял:</b>\n"
            f"{site_sync_error}\n"
            f"Проверь BOT_API_SECRET в боте и на сайте."
        )

    await message.answer(
        f"🎉 <b>ОПЛАТА УСПЕШНА!</b>\n\n"
        f"💎 Premium активирован!\n"
        f"🔑 Ваш код: <code>{vip_code}</code>\n"
        f"📅 До: {format_expiry(expiry)}\n"
        f"⏱ На 30 дней\n\n"
        f"Введите код на сайте:\n"
        f"<b>Настройки → VOID Premium</b>\n\n"
        f"Проверить: /vip | /mycode{sync_note}",
        parse_mode="HTML",
    )

    try:
        await bot.send_message(
            ADMIN_ID,
            f"💰 <b>ПРОДАН Premium!</b>\n"
            f"👤 @{username or 'юзер'} (ID: {user_id})\n"
            f"🔑 Код: <code>{vip_code}</code>\n"
            f"💵 {VIP_PRICE_STARS} ⭐\n"
            f"📅 До: {format_expiry(expiry)}",
            parse_mode="HTML",
        )
    except Exception:
        pass


@dp.message()
async def any_message(message: types.Message):
    user_id = message.from_user.id
    if is_vip_active(user_id):
        code = vip_users[user_id]["code"]
        await message.answer(
            f"👑 <b>VIP</b> | Код: <code>{code}</code>\n\n"
            f"Команды: /vip | /mycode | /help",
            parse_mode="HTML",
        )
    else:
        await message.answer("❌ Нужен Premium\n\nКупить: /buy | /what")


async def sync_local_codes_to_site():
    """При старте: коды из vip_data.json, которых нет на сайте, — регистрируем."""
    for user_id, data in list(vip_users.items()):
        code = data.get("code") or ""
        if not code or len(code) != CODE_LENGTH:
            continue
        if data.get("frozen") or data["expiry"] <= datetime.now():
            continue
        try:
            info = await manage_on_site("info", code=code, telegram_id=user_id)
            if info.get("ok"):
                continue
        except RuntimeError:
            pass
        try:
            await register_code_on_site(user_id, code, data.get("username") or "")
            logger.info("Синхронизирован код %s для TG %s", code, user_id)
        except RuntimeError as err:
            # Уже есть / занят — ок
            if "уже" in str(err).lower() or "exist" in str(err).lower():
                continue
            logger.warning("Не удалось синхронизировать код %s: %s", code, err)


async def outbox_worker():
    """Забирает из сайта очередь сообщений (коды входа) и шлёт в Telegram."""
    await asyncio.sleep(1)
    while True:
        try:
            messages = await pull_telegram_outbox()
            for item in messages:
                if not isinstance(item, dict):
                    continue
                chat_id = int(item.get("chatId") or item.get("chat_id") or 0)
                text = str(item.get("text") or "")
                if chat_id <= 0 or not text:
                    continue
                try:
                    await bot.send_message(chat_id, text, parse_mode="HTML")
                    logger.info("Outbox: сообщение отправлено chat_id=%s", chat_id)
                except Exception as send_err:
                    logger.warning(
                        "Outbox: не удалось отправить chat_id=%s: %s", chat_id, send_err
                    )
        except RuntimeError as err:
            logger.debug("Outbox pull: %s", err)
        except Exception as err:
            logger.warning("Outbox worker: %s", err)
        await asyncio.sleep(OUTBOX_POLL_SEC)


async def main():
    # каталог для vip_data
    try:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    load_data()
    logger.info("Старт VOID-бота…")
    me = await bot.get_me()
    bot_username = me.username or ""
    logger.info("Бот: @%s (id=%s)", bot_username, me.id)
    logger.info("Premium: %s Stars / %s дн. | коды: %s симв.", VIP_PRICE_STARS, SUBSCRIPTION_DAYS, CODE_LENGTH)
    logger.info("SITE_API_URL=%s", SITE_API_URL)
    logger.info("DATA_FILE=%s", DATA_FILE)
    logger.info("В api/config.php: TELEGRAM_BOT_USERNAME = '%s'", bot_username)
    try:
        await sync_local_codes_to_site()
        logger.info("Синхронизация VIP-кодов с сайтом: OK")
    except Exception as err:
        logger.warning("Синхронизация VIP-кодов: %s", err)
    asyncio.create_task(outbox_worker())
    # drop_pending_updates=False — не теряем оплаты/команды при рестарте
    await dp.start_polling(bot, handle_signals=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Остановка по Ctrl+C")
    except Exception:
        logger.exception("Бот упал")
        raise