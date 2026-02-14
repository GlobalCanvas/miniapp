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
                    for canvas in data.get("canvases", []):
                        if canvas.get("ident") == site["canvas_id"]:
                            colors = canvas.get("colors", [])
                            palette = []
                            for i in range(0, len(colors), 3):
                                r, g, b = colors[i], colors[i+1], colors[i+2]
                                palette.append([r, g, b, 255])
                            return palette
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


async def upload_mini(message, bot):
    """
    Команда /upload_mini - завантажити зображення як шаблон для MiniMap
    Зберігає координати в JSON файл для автоматичного використання в check_mini
    
    Args:
        message: Telegram message об'єкт
        bot: Telegram Bot об'єкт
    """
    args = message.text.split()[1:] if message.text else []
    chat_id = message.chat.id
    site_name = get_minimap_site(chat_id)
    site = MINIMAP_SITES[site_name]
    
    if len(args) < 2:
        await message.answer(
            f"📝 <b>MiniMap Upload</b>\n\n"
            f"🌐 <b>Поточний сайт:</b> <code>{site_name}</code>\n"
            f"📏 <b>Розмір карти:</b> {site['canvas_size']}x{site['canvas_size']}\n\n"
            f"Використання: /upload_mini <x> <y>\n\n"
            f"Приклад: /upload_mini -500 300\n\n"
            f"🖼️ Прикріпіть зображення одразу з командою\n"
            f"💡 Змінити сайт: /sitemini",
            parse_mode="HTML"
        )
        return
    
    try:
        x = int(args[0])
        y = int(args[1])
        
        canvas_size = site["canvas_size"]
        
        # Перевірка координат
        if not (-canvas_size//2 <= x < canvas_size//2 and -canvas_size//2 <= y < canvas_size//2):
            await message.answer(
                f"❌ Координати за межами MiniMap!\n"
                f"Діапазон: від {-canvas_size//2} до {canvas_size//2-1}",
                parse_mode="HTML"
            )
            return
        
        if message.photo:
            # Завантаження файлу
            file = await bot.get_file(message.photo[-1].file_id)
            file_bytes = await bot.download_file(file.file_path)
            
            img = Image.open(file_bytes).convert("RGB")
            w, h = img.size
            
            # Збереження шаблону
            filepath = f"templates/minimap_{chat_id}.png"
            info_filepath = f"templates/minimap_{chat_id}_info.json"
            
            img.save(filepath)
            
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
                f"📍 Координати: ({x}, {y})\n"
                f"📐 Розмір: {w}x{h} px\n"
                f"🌐 Сайт: <code>{site_name}</code>\n"
                f"🆔 Canvas: {site['canvas_id']}\n"
                f"📏 Розмір карти: {canvas_size}x{canvas_size}\n\n"
                f"💡 Координати збережено автоматично!\n"
                f"Використайте /check_mini для перевірки прогресу",
                parse_mode="HTML"
            )
        else:
            await message.answer("❌ Прикріпіть зображення!")
            
    except ValueError:
        await message.answer("❌ Невірний формат координат!")
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}")
        import traceback
        traceback.print_exc()


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
            "Використайте /upload_mini <x> <y> щоб завантажити шаблон з координатами",
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
        f"📍 Координати: ({x}, {y})\n"
        f"🌐 Сайт: {saved_site}\n"
        f"🔄 Використовується chunk downloader...",
        parse_mode="HTML"
    )
    
    try:
        # Отримуємо палітру
        palette = await fetch_minimap_palette(saved_site)
        
        # Використовуємо метод download_area з chunk_downloader
        canvas_img = await chunk_downloader.download_area(
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
    canvas_pixels = canvas_img.load()
    
    total_pixels = w * h
    correct_pixels = 0
    wrong_pixels = 0
    
    for py in range(h):
        for px in range(w):
            template_color = template_pixels[px, py]
            canvas_color = canvas_pixels[px, py]
            
            if template_color == canvas_color:
                correct_pixels += 1
            else:
                wrong_pixels += 1
    
    progress_percent = (correct_pixels / total_pixels * 100) if total_pixels > 0 else 0
    
    # Створення різниці
    diff_img = Image.new("RGB", (w, h))
    diff_pixels = diff_img.load()
    
    for py in range(h):
        for px in range(w):
            template_color = template_pixels[px, py]
            canvas_color = canvas_pixels[px, py]
            
            if template_color == canvas_color:
                diff_pixels[px, py] = (0, 255, 0)  # Зелений - правильно
            else:
                diff_pixels[px, py] = (255, 0, 0)  # Червоний - неправильно
    
    # Збереження та відправка
    buf = io.BytesIO()
    diff_img.save(buf, format="PNG")
    buf.seek(0)
    
    caption = (
        f"📊 <b>MiniMap Прогрес Шаблону</b>\n\n"
        f"📍 Позиція: ({x}, {y})\n"
        f"📐 Розмір: {w}x{h} px\n"
        f"🌐 Сайт: <code>{saved_site}</code>\n"
        f"✅ Правильних: {correct_pixels:,} ({progress_percent:.2f}%)\n"
        f"❌ Неправильних: {wrong_pixels:,}\n"
        f"📊 Всього: {total_pixels:,}\n\n"
        f"🟢 Зелений = Правильно\n"
        f"🔴 Червоний = Потрібно виправити"
    )
    
    photo = BufferedInputFile(buf.read(), filename="minimap_diff.png")
    await bot.delete_message(chat_id, progress_msg.message_id)
    await bot.send_photo(chat_id, photo, caption=caption, parse_mode="HTML")


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
            "Використайте /upload_mini <x> <y> щоб завантажити шаблон",
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
