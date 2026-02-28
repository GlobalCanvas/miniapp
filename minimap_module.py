"""
MiniMap Module для pixelya.fun та pixunivers.fun
Працює як звичайний canvas, але окремо від основного

Модуль містить функції:
- sitemini: Перемикання між pixelya та pixunivers для MiniMap
- upload_mini: Завантаження зображення як шаблону для MiniMap
- check_mini: Перевірка прогресу шаблону (автоматично бере координати)
- get_mini: Отримання області з MiniMap (формат: width_height)
"""

import asyncio
import aiohttp
import json
import io
from PIL import Image
from datetime import datetime
from aiogram.types import BufferedInputFile
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext


class UploadMiniStates(StatesGroup):
    waiting_for_file = State()

# Константи для MiniMap
MINIMAP_SITES = {
    "pixelya": {
        "url": "https://pixelya.fun",
        "api_url": "https://pixelya.fun/api/me",
        "chunk_url": "https://pixelya.fun/chunks/{canvas_id}/{x}/{y}.bmp",
        "canvas_id": 0,  # Mini World
        "canvas_size": 32768
    },
    "pixunivers": {
        "url": "https://pixunivers.fun",
        "api_url": "https://pixunivers.fun/api/me",
        "chunk_url": "https://pixunivers.fun/chunks/{canvas_id}/{x}/{y}.bmp",
        "canvas_id": 11,  # Minimap
        "canvas_size": 8192
    }
}

# Файл для збереження налаштувань MiniMap для кожного чату
MINIMAP_SETTINGS_FILE = "minimap_settings.json"


def load_minimap_settings():
    """Завантажує налаштування MiniMap"""
    try:
        with open(MINIMAP_SETTINGS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_minimap_settings(settings):
    """Зберігає налаштування MiniMap"""
    with open(MINIMAP_SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=4)


def get_minimap_site(chat_id):
    """Отримує поточний сайт MiniMap для чату"""
    settings = load_minimap_settings()
    return settings.get(str(chat_id), {}).get("site", "pixelya")


def set_minimap_site(chat_id, site_name):
    """Встановлює сайт MiniMap для чату"""
    settings = load_minimap_settings()
    chat_id_str = str(chat_id)
    if chat_id_str not in settings:
        settings[chat_id_str] = {}
    settings[chat_id_str]["site"] = site_name
    save_minimap_settings(settings)


async def fetch_minimap_palette(site_name):
    """Отримання палітри для MiniMap"""
    site = MINIMAP_SITES[site_name]
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(site["api_url"], timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    canvases = data.get("canvases", [])
                    # API може повертати canvases як список або як словник
                    if isinstance(canvases, dict):
                        canvases = list(canvases.values())
                    for canvas in canvases:
                        # Порівнюємо як рядки бо API може повертати "11" або 11
                        if str(canvas.get("ident", "")) == str(site["canvas_id"]):
                            colors = canvas.get("colors", [])
                            palette = []
                            for i in range(0, len(colors), 3):
                                r, g, b = colors[i], colors[i+1], colors[i+2]
                                palette.append([r, g, b, 255])
                            if palette:
                                print(f"✅ Палітра MiniMap ({site_name}): {len(palette)} кольорів, canvas_id={site['canvas_id']}")
                                return palette
                    # Якщо не знайшли потрібний canvas — логуємо доступні
                    print(f"⚠️ Canvas {site['canvas_id']} не знайдено! Доступні: {[c.get('ident') for c in canvases]}")
    except Exception as e:
        print(f"❌ Помилка отримання палітри MiniMap ({site_name}): {e}")
    
    # Дефолтна палітра якщо не вдалось завантажити
    return [[255, 255, 255, 255], [0, 0, 0, 255]]


async def sitemini(message, bot):
    """
    Команда /sitemini - перемикання сайту для MiniMap
    
    Args:
        message: Telegram message об'єкт
        bot: Telegram Bot об'єкт
    """
    args = message.text.split()[1:] if message.text else []
    chat_id = message.chat.id
    
    if not args:
        current_site = get_minimap_site(chat_id)
        site_list = ", ".join(MINIMAP_SITES.keys())
        
        site_info = MINIMAP_SITES[current_site]
        
        await message.answer(
            f"🗺️ <b>MiniMap Налаштування</b>\n\n"
            f"🌐 <b>Поточний сайт:</b> <code>{current_site}</code>\n"
            f"🆔 <b>Canvas ID:</b> {site_info['canvas_id']}\n"
            f"📏 <b>Розмір:</b> {site_info['canvas_size']}x{site_info['canvas_size']}\n\n"
            f"📝 <b>Доступні сайти:</b> {site_list}\n\n"
            f"Використання: /sitemini <назва_сайту>\n"
            f"Приклад: /sitemini pixunivers",
            parse_mode="HTML"
        )
        return
    
    site_name = args[0].lower()
    
    if site_name not in MINIMAP_SITES:
        site_list = ", ".join(MINIMAP_SITES.keys())
        await message.answer(
            f"❌ Невідомий сайт: <code>{site_name}</code>\n\n"
            f"Доступні: {site_list}",
            parse_mode="HTML"
        )
        return
    
    set_minimap_site(chat_id, site_name)
    site_info = MINIMAP_SITES[site_name]
    
    await message.answer(
        f"✅ <b>MiniMap сайт змінено!</b>\n\n"
        f"🌐 <b>Сайт:</b> <code>{site_name}</code>\n"
        f"🆔 <b>Canvas ID:</b> {site_info['canvas_id']}\n"
        f"📏 <b>Розмір:</b> {site_info['canvas_size']}x{site_info['canvas_size']}",
        parse_mode="HTML"
    )


async def upload_mini(message, bot, state: FSMContext):
    """
    Команда /upload_mini - завантажити зображення як шаблон для MiniMap
    Аналогічно /upload в основному коді — через FSM, координати в підписі X_Y
    
    Args:
        message: Telegram message об'єкт
        bot: Telegram Bot об'єкт
        state: FSMContext об'єкт
    """
    chat_id = message.chat.id
    site_name = get_minimap_site(chat_id)
    site = MINIMAP_SITES[site_name]

    await message.answer(
        f"📤 <b>MiniMap Upload</b>\n\n"
        f"🌐 <b>Поточний сайт:</b> <code>{site_name}</code>\n"
        f"📏 <b>Розмір карти:</b> {site['canvas_size']}x{site['canvas_size']}\n\n"
        f"Надішли PNG файл шаблону з координатами в підписі.\n\n"
        f"Формат підпису: <code>X_Y</code>\n"
        f"Приклад: <code>-500_300</code>\n\n"
        f"💡 Змінити сайт: /sitemini",
        parse_mode="HTML"
    )
    await state.set_state(UploadMiniStates.waiting_for_file)


async def upload_mini_handler(message, bot, state: FSMContext):
    """
    Обробник файлу для /upload_mini (FSM state)
    Приймає документ (без стиснення) з підписом X_Y
    """
    chat_id = message.chat.id

    if not message.document or not message.document.mime_type.startswith("image/"):
        await message.answer("❌ Прикріпи PNG файл (без стиснення — як документ).")
        return

    cap = message.caption or ""
    if "_" not in cap:
        await message.answer(
            "❌ Вкажи координати в підписі у форматі <code>X_Y</code>\n"
            "Приклад: <code>-500_300</code>",
            parse_mode="HTML"
        )
        return

    try:
        coords = cap.strip().split("_")
        x, y = int(coords[0]), int(coords[1])

        site_name = get_minimap_site(chat_id)
        site = MINIMAP_SITES[site_name]
        canvas_size = site["canvas_size"]

        # Перевірка координат
        if not (-canvas_size // 2 <= x < canvas_size // 2 and -canvas_size // 2 <= y < canvas_size // 2):
            await message.answer(
                f"❌ Координати за межами MiniMap!\n"
                f"Діапазон: від {-canvas_size // 2} до {canvas_size // 2 - 1}",
                parse_mode="HTML"
            )
            await state.clear()
            return

        filepath = f"templates/minimap_{chat_id}.png"
        info_filepath = f"templates/minimap_{chat_id}_info.json"

        await bot.download(message.document, filepath)

        with Image.open(filepath) as img:
            w, h = img.size

        # Зберігаємо координати в JSON
        template_info = {
            'x': x,
            'y': y,
            'width': w,
            'height': h,
            'site': site_name,
            'uploaded_at': datetime.now().isoformat()
        }

        with open(info_filepath, 'w') as f:
            json.dump(template_info, f, indent=4)

        await message.answer(
            f"✅ <b>Шаблон MiniMap збережено!</b>\n\n"
            f"📍 <b>Координати:</b> <code>{x}_{y}</code>\n"
            f"📐 <b>Розмір:</b> <code>{w} × {h}</code> px\n"
            f"🌐 <b>Сайт:</b> <code>{site_name}</code>\n"
            f"🆔 <b>Canvas:</b> {site['canvas_id']}\n"
            f"📏 <b>Розмір карти:</b> {canvas_size}x{canvas_size}\n\n"
            f"💡 Використайте /check_mini для перевірки прогресу",
            parse_mode="HTML"
        )
        await state.clear()

    except (ValueError, IndexError):
        await message.answer(
            "❌ Невірний формат координат!\n"
            "Приклад підпису: <code>-500_300</code>",
            parse_mode="HTML"
        )
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")
        import traceback
        traceback.print_exc()
        await state.clear()


async def check_mini(message, bot, chunk_downloader):
    """
    Команда /check_mini - перевірка прогресу шаблону на MiniMap
    Автоматично бере координати з збереженого шаблону
    Використовує chunk_downloader для завантаження чанків
    
    Args:
        message: Telegram message об'єкт
        bot: Telegram Bot об'єкт
        chunk_downloader: ChunkDownloader об'єкт
    """
    chat_id = message.chat.id
    
    # Перевіряємо чи є збережений шаблон з координатами
    template_info_file = f"templates/minimap_{chat_id}_info.json"
    filepath = f"templates/minimap_{chat_id}.png"
    
    try:
        with open(template_info_file, 'r') as f:
            template_info = json.load(f)
            x = template_info['x']
            y = template_info['y']
            saved_site = template_info.get('site', 'pixelya')
    except FileNotFoundError:
        await message.answer(
            "❌ Шаблон не знайдено!\n"
            "Використайте /upload_mini &lt;x&gt; &lt;y&gt; щоб завантажити шаблон з координатами",
            parse_mode="HTML"
        )
        return
    
    try:
        template = Image.open(filepath).convert("RGB")
    except FileNotFoundError:
        await message.answer(
            "❌ Файл шаблону не знайдено!\n"
            "Використайте /upload_mini щоб завантажити шаблон",
            parse_mode="HTML"
        )
        return
    
    w, h = template.size
    
    # Перевіряємо чи збігається сайт
    current_site = get_minimap_site(chat_id)
    if saved_site != current_site:
        await message.answer(
            f"⚠️ <b>Увага!</b>\n\n"
            f"Шаблон був створений для: <code>{saved_site}</code>\n"
            f"Поточний сайт MiniMap: <code>{current_site}</code>\n\n"
            f"Використовується сайт з шаблону: <code>{saved_site}</code>",
            parse_mode="HTML"
        )
    
    site = MINIMAP_SITES[saved_site]
    
    # Прогрес повідомлення
    progress_msg = await message.answer(
        f"⏳ <b>Завантаження MiniMap області {w}x{h}...</b>\n"
        f"📍 <b>Координати:</b> <code>{x}_{y}</code>\n"
        f"🌐 <b>Сайт:</b> {saved_site}\n"
        f"🔄 Використовується chunk downloader...",
        parse_mode="HTML"
    )
    
    try:
        # Отримуємо палітру
        palette = await fetch_minimap_palette(saved_site)
        
        # Використовуємо метод download_area з chunk_downloader
        canvas_img = await chunk_downloader.download_area(
            canvas_size=site["canvas_size"],
            x=x, 
            y=y, 
            w=w, 
            h=h,
            canvas_id=site["canvas_id"],
            palette=palette,
            site_name=saved_site
        )
        
    except Exception as e:
        await bot.delete_message(chat_id, progress_msg.message_id)
        await message.answer(f"❌ Помилка завантаження: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Підрахунок прогресу
    template_pixels = template.load()
    canvas_img_rgba = canvas_img.convert("RGBA")
    canvas_pixels = canvas_img_rgba.load()
    
    total_pixels = w * h
    correct_pixels = 0
    wrong_pixels = 0
    empty_pixels = 0  # Порожні клітинки на канвасі (ще не намальовано)
    
    for py in range(h):
        for px in range(w):
            template_color = template_pixels[px, py]
            canvas_color = canvas_pixels[px, py]
            
            # Якщо alpha = 0 — клітинка порожня, не рахуємо
            if canvas_color[3] == 0:
                empty_pixels += 1
                continue
            
            if template_color[:3] == canvas_color[:3]:
                correct_pixels += 1
            else:
                wrong_pixels += 1
    
    counted_pixels = total_pixels - empty_pixels
    progress_percent = (correct_pixels / counted_pixels * 100) if counted_pixels > 0 else 0
    
    # Створення різниці
    diff_img = Image.new("RGB", (w, h))
    diff_pixels = diff_img.load()
    
    for py in range(h):
        for px in range(w):
            template_color = template_pixels[px, py]
            canvas_color = canvas_pixels[px, py]
            
            if canvas_color[3] == 0:
                diff_pixels[px, py] = (50, 50, 50)  # Сірий — порожньо
            elif template_color[:3] == canvas_color[:3]:
                diff_pixels[px, py] = (0, 255, 0)   # Зелений — правильно
            else:
                diff_pixels[px, py] = (255, 0, 0)   # Червоний — неправильно
    
    # Збереження та відправка
    buf = io.BytesIO()
    diff_img.save(buf, format="PNG")
    buf.seek(0)
    
    caption = (
        f"📊 <b>MiniMap Прогрес Шаблону</b>\n\n"
        f"📍 <b>Позиція:</b> <code>{x}_{y}</code>\n"
        f"📐 Розмір: {w}x{h} px\n"
        f"🌐 Сайт: <code>{saved_site}</code>\n"
        f"✅ Правильних: {correct_pixels:,} ({progress_percent:.2f}%)\n"
        f"❌ Неправильних: {wrong_pixels:,}\n"
        f"⬜ Порожніх (не намальовано): {empty_pixels:,}\n"
        f"📊 Всього враховано: {counted_pixels:,}\n\n"
        f"🟢 Зелений = Правильно\n"
        f"🔴 Червоний = Потрібно виправити\n"
        f"⬛ Сірий = Порожньо"
    )
    
    photo = BufferedInputFile(buf.read(), filename="minimap_diff.png")
    await bot.delete_message(chat_id, progress_msg.message_id)
    await bot.send_photo(chat_id, photo, caption=caption, parse_mode="HTML")


async def debug_mini(message, bot, chunk_downloader):
    """
    Команда /debug_mini - показати поточний стан MiniMap області без порівняння
    Аналогічно /debug для основної карти
    """
    chat_id = message.chat.id

    template_info_file = f"templates/minimap_{chat_id}_info.json"

    try:
        with open(template_info_file, 'r') as f:
            template_info = json.load(f)
            x = template_info['x']
            y = template_info['y']
            w = template_info['width']
            h = template_info['height']
            saved_site = template_info.get('site', 'pixelya')
    except FileNotFoundError:
        await message.answer(
            "❌ Шаблон не знайдено!\n"
            "Використайте /upload_mini щоб завантажити шаблон",
            parse_mode="HTML"
        )
        return

    site = MINIMAP_SITES[saved_site]

    status_msg = await message.answer(
        f"👁️ <b>Завантаження MiniMap...</b>\n"
        f"📍 <code>{x}_{y}</code> | {w}x{h} px\n"
        f"🌐 {saved_site}",
        parse_mode="HTML"
    )

    try:
        palette = await fetch_minimap_palette(saved_site)

        canvas_img = await chunk_downloader.download_area(
            canvas_size=site["canvas_size"],
            x=x,
            y=y,
            w=w,
            h=h,
            canvas_id=site["canvas_id"],
            palette=palette,
            site_name=saved_site
        )

        # Конвертуємо RGBA → RGB для відправки (прозорі = сірі)
        bg = Image.new("RGB", canvas_img.size, (30, 30, 30))
        bg.paste(canvas_img.convert("RGB"), mask=canvas_img.split()[3])
        out = bg

        buf = io.BytesIO()
        out.save(buf, format="PNG")
        buf.seek(0)

        caption = (
            f"🗺️ <b>MiniMap Debug</b>\n\n"
            f"🌐 <b>Сайт:</b> <code>{saved_site}</code>\n"
            f"🆔 <b>Canvas ID:</b> {site['canvas_id']}\n"
            f"📍 <b>Координати:</b> <code>{x}_{y}</code>\n"
            f"📐 <b>Розмір:</b> <code>{w} × {h}</code> px"
        )

        photo = BufferedInputFile(buf.read(), filename="debug_mini.png")
        await bot.delete_message(chat_id, status_msg.message_id)
        await bot.send_photo(chat_id, photo, caption=caption, parse_mode="HTML")

    except Exception as e:
        await bot.delete_message(chat_id, status_msg.message_id)
        await message.answer(f"❌ Помилка: {e}")
        import traceback
        traceback.print_exc()


async def get_mini(message, bot, chunk_downloader=None):
    """
    Команда /get_mini - показати завантажений шаблон MiniMap
    Аналогічно /get для основної карти
    
    Args:
        message: Telegram message об'єкт
        bot: Telegram Bot об'єкт
        chunk_downloader: Не використовується (для сумісності)
    """
    chat_id = message.chat.id
    
    # Отримуємо інформацію про шаблон
    template_info_file = f"templates/minimap_{chat_id}_info.json"
    filepath = f"templates/minimap_{chat_id}.png"
    
    try:
        with open(template_info_file, 'r') as f:
            template_info = json.load(f)
    except FileNotFoundError:
        await message.answer(
            "❌ Шаблон MiniMap не знайдено!\n\n"
            "Використайте /upload_mini &lt;x&gt; &lt;y&gt; щоб завантажити шаблон",
            parse_mode="HTML"
        )
        return
    
    # Перевіряємо чи існує файл
    try:
        # Відправляємо шаблон як документ
        from aiogram.types import FSInputFile
        
        x = template_info['x']
        y = template_info['y']
        w = template_info['width']
        h = template_info['height']
        site = template_info.get('site', 'pixelya')
        uploaded_at = template_info.get('uploaded_at', 'N/A')
        
        site_info = MINIMAP_SITES.get(site, {})
        canvas_id = site_info.get('canvas_id', 'N/A')
        canvas_size = site_info.get('canvas_size', 'N/A')
        
        caption = (
            f"📐 <b>MiniMap Шаблон</b>\n\n"
            f"📍 <b>Координати:</b> <code>{x}_{y}</code>\n"
            f"📐 <b>Розмір:</b> <code>{w} × {h}</code> px\n"
            f"🌐 <b>Сайт:</b> <code>{site}</code>\n"
            f"🆔 <b>Canvas ID:</b> {canvas_id}\n"
            f"📏 <b>Розмір карти:</b> {canvas_size}x{canvas_size}\n"
            f"📅 <b>Завантажено:</b> <code>{uploaded_at[:10] if uploaded_at != 'N/A' else 'N/A'}</code>\n\n"
            f"💡 Змінити сайт: /sitemini"
        )
        
        document = FSInputFile(filepath)
        await message.answer_document(
            document=document, 
            caption=caption, 
            parse_mode="HTML"
        )
        
    except FileNotFoundError:
        await message.answer(
            "❌ Файл шаблону не знайдено!\n\n"
            "Використайте /upload_mini щоб завантажити шаблон заново",
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")
        import traceback
        traceback.print_exc()
