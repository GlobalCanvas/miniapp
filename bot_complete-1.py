import asyncio
import os
import io
import json
import aiohttp
import re
from PIL import Image
from datetime import datetime
import pytz

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, BufferedInputFile, FSInputFile
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Імпортуємо конфігурацію сайтів
from sites_config import SITES, get_site_names, is_valid_site
from chunk_downloader_tg import ChunkDownloader, handle_chunk_download

# Імпортуємо MiniMap модуль
from minimap_module import upload_mini, check_mini, get_mini, sitemini

# ================== FSM STATES ==================
class UploadStates(StatesGroup):
    waiting_for_file = State()

# ================== CONFIG ==================
TOKEN = "7412644873:AAGCi47lnCskvjA5-QkWowFQms862ypkXPQ"
CREATOR_ID = 5268649092  # Ваш Telegram ID

# ================== DATA ==================
medals_db = {}
TEMPLATE_DATA = {}
VOID_CHATS = {}
USER_CONNECTIONS = {}

TEMPLATES_DB_FILE = "templates_db.json"
MEDALS_DB_FILE = "medals_db.json"
VOID_DB_FILE = "void_chats.json"
CONNECTIONS_DB_FILE = "connections_db.json"

os.makedirs("templates", exist_ok=True)

# ================== MEDALS HELPERS ==================
def normalize_username(username):
    """Нормалізує username для пошуку"""
    if not username:
        return None
    username = username.strip()
    if username.startswith('@'):
        username = username[1:]
    return username.lower()

# ================== PERSISTENCE ==================
def load_data():
    global TEMPLATE_DATA, medals_db, VOID_CHATS, USER_CONNECTIONS
    try:
        if os.path.exists(TEMPLATES_DB_FILE):
            with open(TEMPLATES_DB_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                TEMPLATE_DATA = {int(k): v for k, v in data.items()}
        
        if os.path.exists(MEDALS_DB_FILE):
            with open(MEDALS_DB_FILE, 'r', encoding='utf-8') as f:
                medals_db = json.load(f)
        
        if os.path.exists(VOID_DB_FILE):
            with open(VOID_DB_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                VOID_CHATS = {int(k): v for k, v in data.items()}
        
        if os.path.exists(CONNECTIONS_DB_FILE):
            with open(CONNECTIONS_DB_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                USER_CONNECTIONS = {int(k): v for k, v in data.items()}
        
        print("✅ Всі бази даних завантажені.")
    except Exception as e:
        print(f"❌ Помилка завантаження: {e}")


def save_all():
    try:
        with open(TEMPLATES_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(TEMPLATE_DATA, f, ensure_ascii=False, indent=4)
        
        with open(MEDALS_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(medals_db, f, ensure_ascii=False, indent=4)
        
        with open(VOID_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(VOID_CHATS, f, ensure_ascii=False, indent=4)
        
        with open(CONNECTIONS_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(USER_CONNECTIONS, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"❌ Помилка збереження: {e}")


# ================== ADMIN CHECK ==================
async def is_admin_or_creator(message: Message) -> bool:
    """Перевірка чи є користувач адміном або творцем"""
    if message.from_user.id == CREATOR_ID:
        return True
    
    if message.chat.type == "private":
        return True
    
    try:
        member = await message.chat.get_member(message.from_user.id)
        return member.status in ["creator", "administrator"]
    except:
        return False


# ================== VOID MONITORING ==================
last_void_raw = {}


async def void_checker_loop(bot: Bot):
    """Перевіряє void події кожну хвилину"""
    global last_void_raw
    
    while True:
        try:
            for site_name, site_data in SITES.items():
                async with aiohttp.ClientSession() as session:
                    async with session.get(site_data["void_url"], timeout=15) as resp:
                        if resp.status == 200:
                            content = await resp.text()
                            match = re.search(r'[A-Z][a-z]{2},\s\d{1,2}\s[A-Z][a-z]{2}\s\d{4}\s\d{2}:\d{2}:\d{2}\sGMT', content)
                            
                            if match:
                                raw_time_str = match.group(0)
                                if last_void_raw.get(site_name) != raw_time_str:
                                    gmt_format = "%a, %d %b %Y %H:%M:%S GMT"
                                    dt_gmt = datetime.strptime(raw_time_str, gmt_format)
                                    
                                    gmt_zone = pytz.timezone('GMT')
                                    kyiv_zone = pytz.timezone('Europe/Kyiv')
                                    
                                    dt_gmt = gmt_zone.localize(dt_gmt)
                                    dt_kyiv = dt_gmt.astimezone(kyiv_zone)
                                    
                                    kyiv_display = dt_kyiv.strftime("%d.%m.%Y о %H:%M:%S")

                                    for chat_id, chat_data in VOID_CHATS.items():
                                        if chat_data.get("site") == site_name:
                                            try:
                                                text = (
                                                    f"🌌 <b>ВИЯВЛЕНО НОВИЙ ВОЙД!</b>\n\n"
                                                    f"🌐 <b>Сайт:</b> <code>{site_name}</code>\n"
                                                    f"🕐 <b>Час (Київ):</b> <code>{kyiv_display}</code>\n"
                                                    f"🌍 <b>GMT:</b> <code>{raw_time_str}</code>"
                                                )
                                                await bot.send_message(
                                                    chat_id=chat_id,
                                                    text=text,
                                                    parse_mode="HTML"
                                                )
                                            except Exception as e:
                                                print(f"Помилка відправки в чат {chat_id}: {e}")
                                    
                                    last_void_raw[site_name] = raw_time_str
        except Exception as e:
            print(f"Помилка моніторингу: {e}")
        
        await asyncio.sleep(60)  # Кожну хвилину


# ================== PIXEL LOGIC ==================
async def fetch_tile(session, ix, iy, palette, site_name, retries=5):
    """Завантажує один чанк"""
    site = SITES[site_name]
    url = site["chunk_url"].format(x=ix, y=iy)
    
    for attempt in range(retries):
        try:
            async with session.get(url, timeout=20) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    if len(data) != 65536:
                        if attempt < retries - 1:
                            await asyncio.sleep(1)
                            continue
                        return None
                    
                    img = Image.new("RGB", (256, 256))
                    pixels = img.load()
                    for y in range(256):
                        for x in range(256):
                            idx = data[y * 256 + x]
                            pixels[x, y] = tuple(palette[idx][:3]) if idx < len(palette) else (0, 0, 0)
                    return img
                elif resp.status == 404:
                    return Image.new("RGB", (256, 256), color=(0, 0, 0))
        except asyncio.TimeoutError:
            if attempt < retries - 1:
                await asyncio.sleep(2)
                continue
        except Exception as e:
            if attempt < retries - 1:
                await asyncio.sleep(1)
                continue
    
    return Image.new("RGB", (256, 256), color=(0, 0, 0))


async def download_area(canvas_size, x, y, w, h, palette, site_name):
    """Завантажує область карти"""
    offset = int(-canvas_size / 2)
    
    xc_start = (x - offset) // 256
    xc_end = (x + w - 1 - offset) // 256
    yc_start = (y - offset) // 256
    yc_end = (y + h - 1 - offset) // 256
    
    total_chunks = (xc_end - xc_start + 1) * (yc_end - yc_start + 1)
    print(f"📦 Завантаження {total_chunks} чанків для {w}x{h} px")
    
    result = Image.new("RGB", (w, h), color=(0, 0, 0))
    
    connector = aiohttp.TCPConnector(limit=40, limit_per_host=25)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        semaphore = asyncio.Semaphore(25)
        
        async def fetch_and_paste(ix, iy):
            async with semaphore:
                px = (ix * 256 + offset) - x
                py = (iy * 256 + offset) - y
                
                img = await fetch_tile(session, ix, iy, palette, site_name)
                
                if img:
                    try:
                        crop_w = min(256, w - px)
                        crop_h = min(256, h - py)
                        
                        if crop_w > 0 and crop_h > 0:
                            cropped = img.crop((0, 0, crop_w, crop_h))
                            result.paste(cropped, (px, py))
                            cropped.close()
                        
                        img.close()
                    except Exception as e:
                        print(f"❌ Помилка вставки [{ix},{iy}]: {e}")
        
        tasks = []
        for iy in range(yc_start, yc_end + 1):
            for ix in range(xc_start, xc_end + 1):
                tasks.append(fetch_and_paste(ix, iy))
        
        await asyncio.gather(*tasks)
    
    return result


def compare_images_sync(base_img, template_img, tolerance=35, debug=False):
    """Порівняння зображень"""
    w, h = min(base_img.width, template_img.width), min(base_img.height, template_img.height)
    base = base_img.crop((0,0,w,h)).convert("RGBA")
    templ = template_img.crop((0,0,w,h)).convert("RGBA")
    out = templ.copy()
    bp, tp, op = base.load(), templ.load(), out.load()
    matched, total, missing, wrong = 0, 0, 0, 0
    
    for y in range(h):
        for x in range(w):
            if tp[x, y][3] < 128: 
                continue
            
            total += 1
            
            if bp[x, y][3] < 128:
                missing += 1
                if debug:
                    op[x, y] = (255, 128, 0, 255)
                continue
            
            dr = int(bp[x,y][0]) - int(tp[x,y][0])
            dg = int(bp[x,y][1]) - int(tp[x,y][1])
            db = int(bp[x,y][2]) - int(tp[x,y][2])
            distance = (dr*dr + dg*dg + db*db) ** 0.5
            
            if distance <= tolerance:
                matched += 1
                if debug:
                    op[x, y] = (0, 255, 0, 255)
            else:
                wrong += 1
                if debug:
                    op[x, y] = (255, 0, 0, 255)
    
    percent = (matched / total * 100) if total > 0 else 0
    return out, percent, matched, total, missing, wrong


# ================== BOT COMMANDS ==================
async def cmd_start(message: Message):
    """Команда /start"""
    text = (
        "🤖 <b>UkrWay Pixel Monitor Bot</b>\n\n"
        "📋 <b>Доступні команди:</b>\n\n"
        "<b>Шаблон:</b>\n"
        "/upload - Завантажити шаблон\n"
        "/get - Отримати шаблон\n"
        "/check - Перевірити прогрес\n"
        "/debug - Подивитися мапу\n\n"
        "<b>Налаштування:</b>\n"
        "/site - Вибрати сайт\n"
        "/status - Поточні налаштування\n"
        "/sites - Доступні сайти\n\n"
        "<b>Акаунт:</b>\n"
        "/connect - Підключити акаунт\n"
        "/profile - Ваш профіль\n\n"
        "<b>Рейтинг:</b>\n"
        "/top - Топ 15 гравців\n"
        "/topfac - Топ фракції\n\n"
        "<b>Войд:</b>\n"
        "/void - Увімкнути сповіщення\n"
        "/voidtime - Інфо про войд\n\n"
        "<b>🗺️ MiniMap (pixelya/pixunivers):</b>\n"
        "/sitemini - Вибрати сайт для MiniMap\n"
        "/upload_mini x y - Завантажити шаблон\n"
        "/get_mini - Показати шаблон\n"
        "/check_mini - Перевірити прогрес (авто)\n\n"
        "<b>🏆 Медалі:</b>\n"
        "/medals - Переглянути медалі\n"
        "/medals @username - Медалі користувача\n"
        "/madd @user вага назва - Додати (адмін)\n"
        "/mdel @user номер - Видалити (адмін)\n"
        "/mlist - Список всіх (адмін)\n\n"
        "💡 <b>Порада:</b> Надішліть посилання на піксель для автоматичного завантаження!"
    )
    await message.answer(text, parse_mode="HTML")


async def cmd_site(message: Message):
    """Команда /site - зміна сайту"""
    if not await is_admin_or_creator(message):
        await message.answer("❌ Тільки для адмінів!")
        return
    
    args = message.text.split()[1:] if message.text else []
    if len(args) < 1:
        sites = ", ".join(get_site_names())
        await message.answer(f"❌ Використання: /site <назва_сайту>\nДоступні сайти: {sites}")
        return
    
    site_name = args[0]
    if not is_valid_site(site_name):
        sites = ", ".join(get_site_names())
        await message.answer(f"❌ Доступні сайти: {sites}")
        return
    
    chat_id = message.chat.id
    if chat_id not in TEMPLATE_DATA:
        await message.answer("❌ Спочатку завантажте шаблон через /upload")
        return
    
    TEMPLATE_DATA[chat_id]["site"] = site_name
    save_all()
    
    await message.answer(f"✅ Сайт змінено на: <b>{site_name}</b>", parse_mode="HTML")


async def cmd_status(message: Message):
    """Команда /status"""
    chat_id = message.chat.id
    if chat_id not in TEMPLATE_DATA:
        await message.answer("❌ Шаблон не встановлено!")
        return
    
    info = TEMPLATE_DATA[chat_id]
    site = info.get("site", "pixelya")
    void_status = "✅" if chat_id in VOID_CHATS else "❌"
    
    text = (
        f"⚙️ <b>Налаштування чату</b>\n\n"
        f"🌐 <b>Сайт:</b> <code>{site}</code>\n"
        f"📐 <b>Шаблон:</b> <code>{info['width']} × {info['height']}</code> px\n"
        f"📍 <b>Координати:</b> <code>{info['x']}, {info['y']}</code>\n"
        f"🌌 <b>Войд сповіщення:</b> {void_status}"
    )
    
    await message.answer(text, parse_mode="HTML")


async def cmd_upload(message: Message, state: FSMContext):
    """Команда /upload - завантаження шаблону через FSM"""
    if not await is_admin_or_creator(message):
        await message.answer("❌ Тільки для адмінів!")
        return
    
    await message.answer(
        "📤 Надішли PNG файл шаблону з координатами в підписі.\n\n"
        "Формат підпису: `X_Y`\n"
        "Приклад: `-1000_500`",
        parse_mode="Markdown"
    )
    await state.set_state(UploadStates.waiting_for_file)


async def upload_handler(message: Message, state: FSMContext, bot: Bot):
    """Обробник завантаження файлу"""
    if not message.document or not message.document.mime_type.startswith("image/"):
        await message.answer("❌ Прикріпи PNG файл (без стиснення).")
        return
    
    cap = message.caption or ""
    if "_" not in cap:
        await message.answer("❌ Вкажи координати в підписі: `X_Y`", parse_mode="Markdown")
        return
    
    try:
        coords = cap.strip().split("_")
        x, y = int(coords[0]), int(coords[1])
        
        chat_id = message.chat.id
        path = f"templates/chat_{chat_id}.png"
        await bot.download(message.document, path)
        
        with Image.open(path) as img:
            w, h = img.size
        
        current_site = TEMPLATE_DATA.get(chat_id, {}).get("site", "pixelya")
        
        TEMPLATE_DATA[chat_id] = {
            "path": path,
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "site": current_site
        }
        save_all()
        
        await message.answer(
            f"✅ Шаблон завантажено!\n\n"
            f"📏 Розмір: `{w}×{h}` px\n"
            f"📍 Координати: `{x}, {y}`\n"
            f"🌐 Сайт: `{current_site}`",
            parse_mode="Markdown"
        )
        await state.clear()
        
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")
        await state.clear()


async def cmd_get(message: Message):
    """Команда /get - отримати шаблон"""
    chat_id = message.chat.id
    if chat_id not in TEMPLATE_DATA:
        await message.answer("❌ Шаблон не встановлено!")
        return
    
    info = TEMPLATE_DATA[chat_id]
    try:
        caption = (
            f"📐 <b>Шаблон чату</b>\n\n"
            f"📍 <b>Координати:</b> <code>{info['x']}_{info['y']}</code>\n"
            f"📐 <b>Розмір:</b> <code>{info['width']} × {info['height']}</code> px\n"
            f"🌐 <b>Сайт:</b> <code>{info['site']}</code>"
        )
        
        document = FSInputFile(info["path"])
        await message.answer_document(document=document, caption=caption, parse_mode="HTML")
    except:
        await message.answer("❌ Файл шаблону не знайдено!")


async def cmd_check(message: Message):
    """Команда /check - перевірка прогресу"""
    chat_id = message.chat.id
    if chat_id not in TEMPLATE_DATA:
        await message.answer("❌ Шаблон не встановлено!")
        return
    
    info = TEMPLATE_DATA[chat_id]
    site = info.get("site", "pixelya")
    
    try:
        status_msg = await message.answer("⏳ Підготовка...")
        
        async with aiohttp.ClientSession() as s:
            async with s.get(SITES[site]["api_me"]) as r:
                me = await r.json()
        
        canvas = me["canvases"][SITES[site]["canvas_id"]]
        
        await status_msg.edit_text("⏳ Завантаження...")
        
        base = await download_area(
            canvas["size"],
            info["x"],
            info["y"],
            info["width"],
            info["height"],
            canvas["colors"],
            site
        )
        
        await status_msg.edit_text("⏳ Порівняння...")
        
        with Image.open(info["path"]) as t_img:
            result, p, m, t, missing, wrong = compare_images_sync(base, t_img, tolerance=35, debug=True)
        
        await status_msg.edit_text("⏳ Створення звіту...")
        
        out = io.BytesIO()
        result.save(out, format='PNG')
        out.seek(0)
        
        filled = int(p / 5)
        bar = "🟩" * filled + "⬜" * (20 - filled)
        
        caption = (
            f"📊 <b>Прогрес Шаблону</b>\n\n"
            f"{bar}\n"
            f"<b>Завершено: {p:.2f}%</b>\n\n"
            f"🌐 <b>Сайт:</b> <code>{site}</code>\n"
            f"📍 <b>Координати:</b> <code>{info['x']}, {info['y']}</code>\n"
            f"📐 <b>Розмір:</b> <code>{info['width']} × {info['height']}</code> px\n"
            f"🎯 <b>Всього:</b> <code>{t:,}</code> px\n"
            f"✅ <b>Правильно:</b> <code>{m:,}</code> px\n"
            f"❌ <b>Помилки:</b> <code>{t-m:,}</code> px"
        )
        
        photo = BufferedInputFile(out.getvalue(), filename="progress.png")
        await message.answer_photo(photo=photo, caption=caption, parse_mode="HTML")
        await status_msg.delete()
        
    except Exception as e:
        print(f"Помилка check: {e}")
        import traceback
        traceback.print_exc()
        await message.answer(f"❌ Помилка: {e}")


async def cmd_debug(message: Message):
    """Команда /debug - показ карти"""
    chat_id = message.chat.id
    if chat_id not in TEMPLATE_DATA:
        await message.answer("❌ Шаблон не встановлено!")
        return
    
    info = TEMPLATE_DATA[chat_id]
    site = info.get("site", "pixelya")
    
    try:
        status_msg = await message.answer("👁️ Завантаження...")
        
        async with aiohttp.ClientSession() as s:
            async with s.get(SITES[site]["api_me"]) as r:
                me = await r.json()
        
        canvas = me["canvases"][SITES[site]["canvas_id"]]
        
        base = await download_area(
            canvas["size"],
            info["x"],
            info["y"],
            info["width"],
            info["height"],
            canvas["colors"],
            site
        )
        
        out = io.BytesIO()
        base.save(out, format='PNG')
        out.seek(0)
        
        caption = (
            f"🗺️ <b>Мапа Debug</b>\n\n"
            f"🌐 <b>Сайт:</b> <code>{site}</code>\n"
            f"📍 <b>Координати:</b> <code>{info['x']}, {info['y']}</code>\n"
            f"📐 <b>Розмір:</b> <code>{info['width']} × {info['height']}</code> px"
        )
        
        photo = BufferedInputFile(out.getvalue(), filename="debug.png")
        await message.answer_photo(photo=photo, caption=caption, parse_mode="HTML")
        await status_msg.delete()
        
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")


async def cmd_connect(message: Message):
    """Команда /connect - підключення акаунту"""
    args = message.text.split(maxsplit=2)[1:] if message.text else []
    
    if len(args) < 1:
        await message.answer(
            "❌ Використання: /connect <нікнейм> [сайт]\n"
            "Приклад: /connect MyNickname pixelya"
        )
        return
    
    nickname = args[0]
    site_name = args[1] if len(args) > 1 else "pixelya"
    
    if not is_valid_site(site_name):
        sites = ", ".join(get_site_names())
        await message.answer(f"❌ Невідомий сайт! Доступні: {sites}")
        return
    
    try:
        status_msg = await message.answer(f"🔍 Шукаю гравця '{nickname}' на {site_name}...")
        
        print(f"\n🔗 /connect: Шукаємо '{nickname}' на {site_name}")
        
        # Завантажуємо рейтинг
        async with aiohttp.ClientSession() as session:
            async with session.get(SITES[site_name]["api_ranking"], timeout=10) as resp:
                if resp.status != 200:
                    await status_msg.edit_text("❌ Не вдалося завантажити рейтинг!")
                    return
                data = await resp.json()
        
        print(f"   Завантажено ranking: {len(data.get('ranking', []))} гравців")
        print(f"   Завантажено dailyRanking: {len(data.get('dailyRanking', []))} гравців")
        
        # Пошук гравця
        def normalize_name(name):
            return str(name).lower().strip() if name else ""
        
        search_name = normalize_name(nickname)
        player_data = None
        
        print(f"   Шукаємо: '{search_name}' (normalized)")
        
        # Шукаємо в ranking
        for player in data.get("ranking", []):
            if normalize_name(player.get("name", "")) == search_name:
                player_data = player
                print(f"   ✅ Знайдено в ranking: {player.get('name')}")
                break
        
        # Шукаємо в dailyRanking
        if not player_data:
            for player in data.get("dailyRanking", []):
                if normalize_name(player.get("name", "")) == search_name:
                    player_data = player
                    print(f"   ✅ Знайдено в dailyRanking: {player.get('name')}")
                    break
        
        if not player_data:
            print(f"   ❌ Гравця не знайдено!")
            await status_msg.edit_text(
                f"❌ Гравця <b>{nickname}</b> не знайдено в рейтингу на <b>{site_name}</b>!\n\n"
                f"💡 Переконайтесь що:\n"
                f"• Нікнейм вірний\n"
                f"• Гравець є в топ рейтингу\n"
                f"• Вибраний правильний сайт",
                parse_mode="HTML"
            )
            return
        
        # Зберігаємо підключення
        USER_CONNECTIONS[message.from_user.id] = {
            "site": site_name,
            "nickname": player_data.get("name")
        }
        save_all()
        
        # Інфо
        total_pixels = player_data.get("px", player_data.get("t", 0))
        
        faction_name = "Н/Д"
        fac_info = player_data.get("facInfo")
        if fac_info and len(fac_info) >= 2:
            faction_name = f"{fac_info[1]} {fac_info[0]}"
        
        text = (
            f"✅ <b>Акаунт успішно підключено!</b>\n\n"
            f"🌐 <b>Сайт:</b> <code>{site_name}</code>\n"
            f"👤 <b>Нікнейм:</b> <code>{player_data.get('name')}</code>\n"
            f"🎨 <b>Всього пікселів:</b> <code>{total_pixels:,}</code>\n"
        )
        
        if faction_name != "Н/Д":
            text += f"🚩 <b>Фракція:</b> <code>{faction_name}</code>\n"
        
        text += "\nВикористовуйте /profile щоб переглянути повну статистику"
        
        await status_msg.edit_text(text, parse_mode="HTML")
        
    except Exception as e:
        print(f"❌ Помилка connect: {e}")
        import traceback
        traceback.print_exc()
        await message.answer(f"❌ Помилка: {e}")


async def cmd_profile(message: Message):
    """Команда /profile - профіль користувача"""
    user_id = message.from_user.id
    
    if user_id not in USER_CONNECTIONS:
        await message.answer(
            "❌ Підключіть свій акаунт спочатку через /connect <нікнейм>!"
        )
        return
    
    conn = USER_CONNECTIONS[user_id]
    site_name = conn["site"]
    nickname = conn["nickname"]
    
    try:
        status_msg = await message.answer("🔍 Завантаження профілю...")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(SITES[site_name]["api_ranking"], timeout=10) as resp:
                if resp.status != 200:
                    await status_msg.edit_text("❌ Не вдалося завантажити рейтинг!")
                    return
                ranking_data = await resp.json()
        
        def normalize_name(name):
            return str(name).lower().strip() if name else ""
        
        search_name = normalize_name(nickname)
        player_data = None
        
        # Шукаємо в ranking
        for player in ranking_data.get("ranking", []):
            if normalize_name(player.get("name", "")) == search_name:
                player_data = player
                break
        
        # Шукаємо в dailyRanking
        if not player_data:
            for player in ranking_data.get("dailyRanking", []):
                if normalize_name(player.get("name", "")) == search_name:
                    player_data = player
                    break
        
        if not player_data:
            await status_msg.edit_text(
                f"❌ Гравця <code>{nickname}</code> не знайдено в рейтингу!\n"
                f"💡 Спробуйте перепідключитися через /connect",
                parse_mode="HTML"
            )
            return
        
        # Дані
        username = player_data.get("name", "Unknown")
        total_pixels = player_data.get("px", player_data.get("t", 0))
        age = player_data.get("age", 0)
        
        faction_name = "Н/Д"
        faction_tag = ""
        fac_info = player_data.get("facInfo")
        if fac_info and len(fac_info) >= 2:
            faction_tag = fac_info[0]
            faction_name = fac_info[1]
        
        # Денні дані
        daily_pixels = 0
        global_rank = "Н/Д"
        daily_rank = "Н/Д"
        
        for player in ranking_data.get("dailyRanking", []):
            if normalize_name(player.get("name", "")) == search_name:
                daily_pixels = player.get("dt", 0)
                global_rank = player.get("r", "Н/Д")
                daily_rank = player.get("dr", "Н/Д")
                break
        
        if global_rank == "Н/Д" and "r" in player_data:
            global_rank = player_data.get("r", "Н/Д")
        
        text = (
            f"👤 <b>Профіль: {username}</b>\n\n"
            f"🌐 <b>Сайт:</b> <code>{site_name}</code>\n"
            f"🏆 <b>Глобальний ранг:</b> #{global_rank}\n"
            f"📅 <b>Денний ранг:</b> #{daily_rank}\n"
            f"🎨 <b>Всього пікселів:</b> <code>{total_pixels:,}</code>\n"
            f"📊 <b>Сьогодні:</b> <code>{daily_pixels:,}</code>\n"
            f"⏳ <b>Вік:</b> <code>{age}</code> днів\n"
        )
        
        if faction_name != "Н/Д":
            text += f"🚩 <b>Фракція:</b> <code>{faction_name} {faction_tag}</code>\n"
        
        # Медалі
        if str(user_id) in medals_db and medals_db[str(user_id)].get("medals"):
            text += "\n🏅 <b>Медалі:</b>\n"
            for m in medals_db[str(user_id)]["medals"][:5]:
                stars = "⭐" * m["weight"]
                text += f"• {m['name']} {stars}\n"
        
        await status_msg.edit_text(text, parse_mode="HTML")
        
    except Exception as e:
        print(f"Помилка profile: {e}")
        import traceback
        traceback.print_exc()
        await message.answer(f"❌ Помилка: {e}")


async def cmd_top(message: Message):
    """Команда /top - топ 15 гравців"""
    chat_id = message.chat.id
    site = TEMPLATE_DATA.get(chat_id, {}).get("site", "pixelya")
    
    try:
        status_msg = await message.answer("🔍 Завантаження рейтингу...")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(SITES[site]["api_ranking"], timeout=10) as resp:
                if resp.status != 200:
                    await status_msg.edit_text("❌ Не вдалося завантажити рейтинг!")
                    return
                data = await resp.json()
        
        daily_ranking = data.get("dailyRanking", [])
        
        if not daily_ranking:
            await status_msg.edit_text("❌ Рейтинг порожній!")
            return
        
        text = f"🏆 <b>ТОП 15 ГРАВЦІВ ({site})</b>\n\n"
        
        for i, player in enumerate(daily_ranking[:15], 1):
            name = player.get("name", "Unknown")
            daily_pixels = player.get("dt", 0)
            total_pixels = player.get("t", 0)
            
            medal = ""
            if i == 1:
                medal = "🥇"
            elif i == 2:
                medal = "🥈"
            elif i == 3:
                medal = "🥉"
            
            text += (
                f"{medal} <b>{i}. {name}</b>\n"
                f"📅 Сьогодні: <code>{daily_pixels:,}</code> px | "
                f"📊 Всього: <code>{total_pixels:,}</code> px\n\n"
            )
        
        await status_msg.edit_text(text, parse_mode="HTML")
        
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")


async def cmd_topfac(message: Message):
    """Команда /topfac - топ фракції"""
    args = message.text.split()[1:] if message.text else []
    
    if len(args) < 1:
        await message.answer(
            "❌ Використання: /topfac <назва_фракції>\n"
            "Приклад: /topfac UkrWay"
        )
        return
    
    faction_name = " ".join(args)
    chat_id = message.chat.id
    site = TEMPLATE_DATA.get(chat_id, {}).get("site", "pixelya")
    
    try:
        status_msg = await message.answer(f"🔍 Пошук фракції '{faction_name}'...")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(SITES[site]["api_ranking"], timeout=10) as resp:
                if resp.status != 200:
                    await status_msg.edit_text("❌ Не вдалося завантажити рейтинг!")
                    return
                data = await resp.json()
        
        def normalize(text):
            if not text:
                return ""
            import re
            return re.sub(r'[^a-z0-9]', '', str(text).lower())
        
        search_normalized = normalize(faction_name)
        
        # Спеціальні випадки для популярних фракцій
        faction_aliases = {
            "ukrway": ["ukrway", "ukwy", "ukrwayreborn", "ukraineway", "ukraway"],
            "ukwy": ["ukrway", "ukwy", "ukrwayreborn", "ukraineway", "ukraway"],
            "ukraineway": ["ukrway", "ukwy", "ukrwayreborn", "ukraineway", "ukraway"],
            "reborn": ["ukrwayreborn", "reborn"],
        }
        
        # Якщо є алаяси, використовуємо їх
        search_variants = faction_aliases.get(search_normalized, [search_normalized])
        
        faction_players = []
        actual_faction_name = None
        actual_faction_tag = None
        
        for player in data.get("ranking", []):
            fac_info = player.get("facInfo")
            
            if fac_info and len(fac_info) >= 2:
                tag = str(fac_info[0])
                name = str(fac_info[1])
                
                tag_normalized = normalize(tag)
                name_normalized = normalize(name)
                
                # Перевіряємо співпадіння з будь-яким варіантом пошуку
                match_found = False
                for variant in search_variants:
                    # Строгіша перевірка співпадіння
                    if len(variant) >= 3:  # Мінімум 3 символи для пошуку
                        if (tag_normalized == variant or 
                            name_normalized == variant or
                            (len(tag_normalized) > 3 and tag_normalized.startswith(variant)) or
                            (len(name_normalized) > 3 and name_normalized.startswith(variant)) or
                            (len(variant) > 3 and variant.startswith(tag_normalized) and len(tag_normalized) >= 3) or
                            (len(variant) > 3 and variant.startswith(name_normalized) and len(name_normalized) >= 3)):
                            match_found = True
                            break
                
                if match_found:
                    faction_players.append(player)
                    
                    if not actual_faction_name:
                        actual_faction_name = name
                        actual_faction_tag = tag
        
        if not faction_players:
            # Збираємо список всіх унікальних фракцій
            all_factions = set()
            similar_factions = set()
            
            for player in data.get("ranking", []):
                fac_info = player.get("facInfo")
                if fac_info and len(fac_info) >= 2:
                    tag = str(fac_info[0])
                    name = str(fac_info[1])
                    faction_str = f"{name} [{tag}]"
                    all_factions.add(faction_str)
                    
                    # Шукаємо схожі фракції
                    tag_norm = normalize(tag)
                    name_norm = normalize(name)
                    if (search_normalized in tag_norm or 
                        search_normalized in name_norm or
                        tag_norm in search_normalized or
                        name_norm in search_normalized):
                        similar_factions.add(faction_str)
            
            error_msg = f"❌ Гравців фракції <code>{faction_name}</code> не знайдено!\n\n"
            
            if similar_factions:
                similar_list = "\n".join(sorted(list(similar_factions)))
                error_msg += f"🔍 <b>Схожі фракції:</b>\n<code>{similar_list}</code>\n\n"
            
            factions_list = "\n".join(sorted(list(all_factions))[:20])
            error_msg += f"💡 <b>Доступні фракції (перші 20):</b>\n<code>{factions_list}</code>"
            
            await status_msg.edit_text(error_msg, parse_mode="HTML")
            return
        
        faction_players.sort(key=lambda x: x.get("px", 0), reverse=True)
        
        text = f"🚩 <b>{actual_faction_name} [{actual_faction_tag}]</b>\n"
        text += f"Топ гравців фракції на <b>{site}</b>\n\n"
        
        daily_data = data.get("dailyRanking", [])
        
        for i, player in enumerate(faction_players[:15], 1):
            name = player.get("name", "Unknown")
            total_pixels = player.get("px", 0)
            
            daily_pixels = 0
            for daily_player in daily_data:
                if daily_player.get("name", "").lower() == name.lower():
                    daily_pixels = daily_player.get("dt", 0)
                    break
            
            medal = ""
            if i == 1:
                medal = "🥇"
            elif i == 2:
                medal = "🥈"
            elif i == 3:
                medal = "🥉"
            
            text += (
                f"{medal} <b>{i}. {name}</b>\n"
                f"📅 Сьогодні: <code>{daily_pixels:,}</code> | "
                f"📊 Всього: <code>{total_pixels:,}</code>\n\n"
            )
        
        await status_msg.edit_text(text, parse_mode="HTML")
        
    except Exception as e:
        print(f"Помилка topfac: {e}")
        import traceback
        traceback.print_exc()
        await message.answer(f"❌ Помилка: {e}")


async def cmd_sites(message: Message):
    """Команда /sites"""
    sites_list = get_site_names()
    text = (
        "🌐 <b>Доступні сайти:</b>\n\n"
        + "\n".join([f"• <code>{site}</code>" for site in sites_list])
    )
    await message.answer(text, parse_mode="HTML")


async def cmd_voidtime(message: Message):
    """Команда /voidtime"""
    args = message.text.split()[1:] if message.text else []
    site_name = args[0] if args else "pixelya"
    
    if not is_valid_site(site_name):
        await message.answer(f"❌ Невірний сайт! Використовуйте /sites щоб побачити доступні сайти.")
        return
    
    try:
        site = SITES[site_name]
        async with aiohttp.ClientSession() as session:
            async with session.get(site["void_url"], timeout=10) as resp:
                if resp.status == 200:
                    # Проверяем, JSON это или текст
                    content_type = resp.headers.get('Content-Type', '')
                    
                    if 'application/json' in content_type:
                        # JSON формат
                        data = await resp.json()
                        
                        next_void = data.get("nextvoid", "N/A")
                        next_void_in = data.get("nextVoidIn", "N/A")
                        chaos_event_time = data.get("chaosEventTime", "N/A")
                        voidinfo = data.get("voidinfo", "N/A")
                        
                        kyiv_time = "Н/Д"
                        is_active = False
                        
                        if next_void != "N/A":
                            try:
                                gmt_format = "%a, %d %b %Y %H:%M:%S GMT"
                                dt_gmt = datetime.strptime(next_void, gmt_format)
                                
                                # Конвертируем GMT в киевское время
                                gmt_zone = pytz.timezone('GMT')
                                kyiv_zone = pytz.timezone('Europe/Kyiv')
                                
                                dt_gmt = gmt_zone.localize(dt_gmt)
                                dt_kyiv = dt_gmt.astimezone(kyiv_zone)
                                
                                kyiv_time = dt_kyiv.strftime("%d.%m.%Y о %H:%M:%S")
                                
                                # Проверяем, активен ли void (время в прошлом)
                                now_utc = datetime.now(pytz.utc)
                                is_active = dt_gmt.astimezone(pytz.utc) < now_utc
                            except Exception as e:
                                print(f"Помилка конвертації часу: {e}")
                                kyiv_time = next_void
                        
                        status = "🟢 АКТИВНИЙ" if is_active else "🔴 НЕАКТИВНИЙ"
                        
                        text = f"🌌 <b>Статус Войду: {site_name}</b>\n\n"
                        text += f"📊 <b>Статус:</b> {status}\n\n"
                        
                        if is_active:
                            text += f"⏰ <b>Почався:</b> <code>{kyiv_time} (Київ)</code>\n"
                            if next_void_in != "N/A":
                                text += f"⏳ <b>Був:</b> <code>{next_void_in}</code>\n"
                            if voidinfo != "N/A":
                                text += f"⏱️ <b>Час до закінчення:</b> <code>{voidinfo}</code>\n"
                        else:
                            text += f"⏰ <b>Наступний войд:</b> <code>{kyiv_time} (Київ)</code>\n"
                            if next_void_in != "N/A" and "last void" in next_void_in.lower():
                                text += f"⏳ <b>Попередній:</b> <code>{next_void_in}</code>\n"
                            if voidinfo != "N/A" and "N/A" in voidinfo.lower():
                                text += f"❌ <b>Час до Закінчення:</b> <code>{voidinfo}</code>\n"
                        
                        # Отображаем chaos event если он активен
                        if chaos_event_time != "N/A" and chaos_event_time != "0hours, 0minutes, 0seconds.":
                            # Форматируем время chaos event
                            chaos_formatted = chaos_event_time.replace("hours", "год").replace("minutes", "хв").replace("seconds", "сек")
                            text += f"⚡ <b>Chaos подія через:</b> <code>{chaos_formatted}</code>\n"
                        
                    else:
                        # Текстовый формат (старый метод)
                        content = await resp.text()
                        
                        time_match = re.search(r'[A-Z][a-z]{2},\s\d{1,2}\s[A-Z][a-z]{2}\s\d{4}\s\d{2}:\d{2}:\d{2}\sGMT', content)
                        active_match = re.search(r'Void is active: (true|false)', content)
                        next_void_match = re.search(r'Next void in: (.*?)(?=\n|$)', content)
                        chaos_match = re.search(r'Chaos event in: (.*?)(?=\n|$)', content)
                        
                        kyiv_time = "Н/Д"
                        
                        if time_match:
                            try:
                                gmt_time_str = time_match.group(0)
                                gmt_format = "%a, %d %b %Y %H:%M:%S GMT"
                                dt_gmt = datetime.strptime(gmt_time_str, gmt_format)
                                
                                gmt_zone = pytz.timezone('GMT')
                                kyiv_zone = pytz.timezone('Europe/Kyiv')
                                
                                dt_gmt = gmt_zone.localize(dt_gmt)
                                dt_kyiv = dt_gmt.astimezone(kyiv_zone)
                                
                                kyiv_time = dt_kyiv.strftime("%d.%m.%Y о %H:%M:%S")
                            except Exception as e:
                                print(f"Помилка конвертації часу: {e}")
                                kyiv_time = time_match.group(0)
                        
                        is_active = active_match.group(1) == "true" if active_match else False
                        next_void_in = next_void_match.group(1).strip() if next_void_match else "Н/Д"
                        chaos_event_time = chaos_match.group(1).strip() if chaos_match else "Н/Д"
                        voidinfo = data.get("voidinfo", "N/A")
                        
                        status = "🟢 АКТИВНИЙ" if is_active else "🔴 НЕАКТИВНИЙ"
                        
                        text = f"🌌 <b>Статус Войду: {site_name}</b>\n\n"
                        text += f"📊 <b>Статус:</b> {status}\n\n"
                        
                        if is_active:
                            text += f"⏰ <b>Почався:</b> <code>{kyiv_time} (Київ)</code>\n"
                            if next_void_in != "Н/Д":
                                text += f"⏳ <b>Почався в:</b> <code>{next_void_in}</code>\n"
                            if voidinfo != "N/A":
                                text += f"⏱️ <b>Час до закінчення:</b> <code>{voidinfo}</code>\n"
                        else:
                            text += f"⏰ <b>Наступний войд:</b> <code>{kyiv_time} (Київ)</code>\n"
                            if next_void_in != "Н/Д":
                                text += f"⏳ <b>Останній войд:</b> <code>{next_void_in}</code>\n"
                            if voidinfo != "N/A" and "N/A" in voidinfo.lower():
                                text += f"❌ <b>Час до Закінчення:</b> <code>{voidinfo}</code>\n"
                        
                        if chaos_event_time != "Н/Д" and chaos_event_time != "0hours, 0minutes, 0seconds.":
                            text += f"⚡ <b>Chaos подія:</b> <code>{chaos_event_time}</code>\n"
                    
                    await message.answer(text, parse_mode="HTML")
                else:
                    await message.answer(f"❌ Помилка підключення (Статус: {resp.status})")
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")


async def cmd_void(message: Message):
    """Команда /void - перемикання сповіщень про void"""
    if not await is_admin_or_creator(message):
        await message.answer("❌ Тільки для адмінів!")
        return
    
    chat_id = message.chat.id
    
    if chat_id not in TEMPLATE_DATA:
        site = "pixelya"
    else:
        site = TEMPLATE_DATA[chat_id].get("site", "pixelya")
    
    if chat_id in VOID_CHATS:
        del VOID_CHATS[chat_id]
        text = "🔴 Сповіщення про войд <b>ВИМКНЕНО</b>"
    else:
        VOID_CHATS[chat_id] = {"site": site}
        text = f"🔔 Сповіщення про войд <b>УВІМКНЕНО</b> для <code>{site}</code>"
    
    save_all()
    await message.answer(text, parse_mode="HTML")


async def cmd_medals(message: Message):
    """Команда /medals - показати медалі по @username"""
    args = message.text.split()[1:] if message.text else []
    
    if args:
        target_username = normalize_username(args[0])
        if not target_username:
            await message.answer("❌ Невірний формат username!")
            return
        display_name = f"@{target_username}"
    else:
        if not message.from_user.username:
            await message.answer(
                "❌ У вас немає username в Telegram!\n"
                "Встановіть username або використайте /medals @username"
            )
            return
        target_username = normalize_username(message.from_user.username)
        display_name = message.from_user.first_name or f"@{target_username}"
    
    if target_username not in medals_db or not medals_db[target_username].get("medals"):
        if args:
            await message.answer(f"У користувача @{target_username} немає медалей.")
        else:
            await message.answer("У вас ще немає медалей.")
        return
    
    user_data = medals_db[target_username]
    text = f"🏆 <b>Медалі: {display_name}</b>\n\n"
    
    for i, m in enumerate(user_data["medals"], 1):
        stars = "⭐" * m["weight"]
        text += f"{i}. <b>{m['name']}</b>\n{stars}\n"
        if m.get("date"):
            text += f"   📅 {m['date']}\n"
        text += "\n"
    
    await message.answer(text, parse_mode="HTML")


async def cmd_madd(message: Message):
    """Команда /madd - додати медаль по @username"""
    if not await is_admin_or_creator(message):
        await message.answer("❌ Тільки для адмінів!")
        return
    
    args = message.text.split(maxsplit=3)[1:] if message.text else []
    
    if len(args) < 3:
        await message.answer(
            "❌ Використання: /madd @username <вага> <назва_медалі>\n\n"
            "Приклад: /madd @john_doe 5 Кращий Піксель Артист\n\n"
            "Вага: від 1 до 10 зірочок ⭐"
        )
        return
    
    try:
        username = normalize_username(args[0])
        if not username:
            await message.answer("❌ Невірний формат username!")
            return
        
        weight = int(args[1])
        medal_name = args[2]
        
        if weight < 1 or weight > 10:
            await message.answer("❌ Вага має бути від 1 до 10!")
            return
        
        if username not in medals_db:
            medals_db[username] = {"username": username, "medals": []}
        
        medals_db[username]["medals"].append({
            "name": medal_name,
            "weight": weight,
            "date": datetime.now().strftime("%Y-%m-%d")
        })
        
        save_all()
        
        stars = "⭐" * weight
        text = (
            f"✅ <b>Медаль додано!</b>\n\n"
            f"👤 <b>Користувач:</b> @{username}\n"
            f"🏅 <b>Медаль:</b> {medal_name}\n"
            f"⭐ <b>Вага:</b> {stars}"
        )
        await message.answer(text, parse_mode="HTML")
        
    except ValueError:
        await message.answer("❌ Невірний формат ваги! Вага має бути числом від 1 до 10.")
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")


async def cmd_mdel(message: Message):
    """Команда /mdel - видалити медаль по @username"""
    if not await is_admin_or_creator(message):
        await message.answer("❌ Тільки для адмінів!")
        return
    
    args = message.text.split()[1:] if message.text else []
    
    if len(args) < 2:
        await message.answer(
            "❌ Використання: /mdel @username <номер_медалі>\n\n"
            "Приклад: /mdel @john_doe 1\n\n"
            "Щоб дізнатись номер медалі, використайте /medals @username"
        )
        return
    
    try:
        username = normalize_username(args[0])
        if not username:
            await message.answer("❌ Невірний формат username!")
            return
        
        index = int(args[1])
        
        if username not in medals_db or not medals_db[username].get("medals"):
            await message.answer(f"❌ У користувача @{username} немає медалей!")
            return
        
        if index < 1 or index > len(medals_db[username]["medals"]):
            await message.answer(
                f"❌ Невірний номер медалі!\n"
                f"У користувача @{username} всього {len(medals_db[username]['medals'])} медалей"
            )
            return
        
        removed = medals_db[username]["medals"].pop(index - 1)
        save_all()
        
        text = (
            f"✅ <b>Медаль видалено!</b>\n\n"
            f"👤 Користувач: @{username}\n"
            f"🏅 Медаль: {removed['name']}"
        )
        await message.answer(text, parse_mode="HTML")
        
    except ValueError:
        await message.answer("❌ Невірний формат номера медалі!")
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")


async def cmd_mlist(message: Message):
    """Команда /mlist - показати всіх з медалями"""
    if not await is_admin_or_creator(message):
        await message.answer("❌ Тільки для адмінів!")
        return
    
    if not medals_db:
        await message.answer("📋 База медалей порожня")
        return
    
    text = "📋 <b>Користувачі з медалями:</b>\n\n"
    
    for username, data in medals_db.items():
        medal_count = len(data.get("medals", []))
        if medal_count > 0:
            text += f"👤 @{username} - {medal_count} медалей\n"
    
    await message.answer(text, parse_mode="HTML")


# ================== MINIMAP COMMANDS ==================
async def cmd_sitemini(message: Message):
    """Команда /sitemini - вибір сайту для MiniMap"""
    await sitemini(message, message.bot)


async def cmd_upload_mini(message: Message):
    """Команда /upload_mini"""
    await upload_mini(message, message.bot)


async def cmd_check_mini(message: Message):
    """Команда /check_mini"""
    chunk_downloader = message.bot.get('chunk_downloader')
    await check_mini(message, message.bot, chunk_downloader)


async def cmd_get_mini(message: Message):
    """Команда /get_mini - показати завантажений шаблон"""
    await get_mini(message, message.bot)


# ================== MESSAGE HANDLER ==================
async def handle_message(message: Message, chunk_downloader: ChunkDownloader):
    """Обробка всіх повідомлень"""
    if message.text:
        await handle_chunk_download(message, chunk_downloader)


# ================== MAIN ==================
async def main():
    load_data()
    
    print("=" * 60)
    print("🤖 UkrWay Pixel Monitor Bot (Telegram) запущено!")
    print("=" * 60)
    print(f"👑 ID Творця: {CREATOR_ID}")
    print(f"📊 Завантажено шаблонів: {len(TEMPLATE_DATA)}")
    print("=" * 60)
    
    # Ініціалізація бота з FSM
    bot = Bot(
        token=TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    chunk_downloader = ChunkDownloader(bot)
    
    # Зберігаємо chunk_downloader в bot для MiniMap команд
    bot['chunk_downloader'] = chunk_downloader
    
    # Реєстрація команд
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_site, Command("site"))
    dp.message.register(cmd_status, Command("status"))
    dp.message.register(cmd_upload, Command("upload"))
    dp.message.register(cmd_get, Command("get"))
    dp.message.register(cmd_check, Command("check"))
    dp.message.register(cmd_debug, Command("debug"))
    dp.message.register(cmd_connect, Command("connect"))
    dp.message.register(cmd_profile, Command("profile"))
    dp.message.register(cmd_top, Command("top"))
    dp.message.register(cmd_topfac, Command("topfac"))
    dp.message.register(cmd_sites, Command("sites"))
    dp.message.register(cmd_voidtime, Command("voidtime"))
    dp.message.register(cmd_void, Command("void"))
    dp.message.register(cmd_medals, Command("medals"))
    dp.message.register(cmd_madd, Command("madd"))
    dp.message.register(cmd_mdel, Command("mdel"))
    dp.message.register(cmd_mlist, Command("mlist"))
    
    # MiniMap команди
    dp.message.register(cmd_sitemini, Command("sitemini"))
    dp.message.register(cmd_upload_mini, Command("upload_mini"))
    dp.message.register(cmd_check_mini, Command("check_mini"))
    dp.message.register(cmd_get_mini, Command("get_mini"))
    
    # Реєстрація FSM обробника для upload
    async def upload_state_handler(msg: Message, state: FSMContext):
        await upload_handler(msg, state, bot)
    
    dp.message.register(upload_state_handler, UploadStates.waiting_for_file)
    
    # Реєстрація обробника повідомлень
    async def message_handler(msg: Message):
        await handle_message(msg, chunk_downloader)
    
    dp.message.register(message_handler, F.text)
    
    # Запуск void моніторингу
    asyncio.create_task(void_checker_loop(bot))
    
    # Запуск бота
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
