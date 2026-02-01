# chunk_downloader_tg.py
"""
Модуль для автоматичного завантаження чанків з посилань (Telegram версія)
"""

import asyncio
import aiohttp
import io
import re
from PIL import Image
from aiogram import Bot
from aiogram.types import Message, BufferedInputFile
from sites_config import SITES


class ChunkDownloader:
    def __init__(self, bot: Bot):
        self.bot = bot
    
    def detect_pixel_link(self, message_text):
        """Визначає pixel сайт та координати з посилання"""
        for site_name, site_config in SITES.items():
            pattern = site_config["link_pattern"]
            match = re.search(pattern, message_text)
            if match:
                x = int(match.group(1))
                y = int(match.group(2))
                zoom = int(match.group(3))
                return site_name, x, y, zoom
        return None
    
    async def download_chunk_area(self, site_name, center_x, center_y, zoom):
        """
        Завантажує область навколо координат
        Zoom визначає розмір області:
        - zoom 1-3: 256x256 (1 chunk)
        - zoom 4-6: 512x512 (4 chunks)
        - zoom 7+: 768x768 (9 chunks)
        """
        if zoom <= 3:
            chunk_size = 1  # 1x1 chunks
        elif zoom <= 6:
            chunk_size = 2  # 2x2 chunks
        else:
            chunk_size = 3  # 3x3 chunks
        
        site_config = SITES[site_name]
        
        try:
            # Отримуємо палітру кольорів
            async with aiohttp.ClientSession() as session:
                async with session.get(site_config["api_me"], timeout=10) as resp:
                    if resp.status != 200:
                        return None, "Failed to get canvas data"
                    
                    data = await resp.json()
                    canvas = data["canvases"][site_config["canvas_id"]]
                    palette = canvas["colors"]
                    canvas_size = canvas["size"]
            
            # Визначаємо які чанки потрібно завантажити
            offset = int(-canvas_size / 2)
            
            # Центральний чанк
            center_chunk_x = (center_x - offset) // 256
            center_chunk_y = (center_y - offset) // 256
            
            # Розмір області в пікселях
            area_size = chunk_size * 256
            
            # Стартові координати
            start_x = center_x - area_size // 2
            start_y = center_y - area_size // 2
            
            # Завантажуємо область
            result = await self.download_area(
                canvas_size, start_x, start_y, 
                area_size, area_size, 
                palette, site_name
            )
            
            return result, None
            
        except Exception as e:
            return None, str(e)
    
    async def fetch_tile(self, session, ix, iy, palette, site_name, retries=3):
        """Завантажує один чанк"""
        site = SITES[site_name]
        url = site["chunk_url"].format(x=ix, y=iy)
        
        for attempt in range(retries):
            try:
                async with session.get(url, timeout=15) as resp:
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
                    await asyncio.sleep(1)
                    continue
            except Exception as e:
                if attempt < retries - 1:
                    await asyncio.sleep(1)
                    continue
        
        return Image.new("RGB", (256, 256), color=(0, 0, 0))
    
    async def download_area(self, canvas_size, x, y, w, h, palette, site_name):
        """Завантажує область карти"""
        offset = int(-canvas_size / 2)
        
        xc_start = (x - offset) // 256
        xc_end = (x + w - 1 - offset) // 256
        yc_start = (y - offset) // 256
        yc_end = (y + h - 1 - offset) // 256
        
        result = Image.new("RGB", (w, h), color=(0, 0, 0))
        
        connector = aiohttp.TCPConnector(limit=20, limit_per_host=15)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            semaphore = asyncio.Semaphore(15)
            
            async def fetch_and_paste(ix, iy):
                async with semaphore:
                    px = (ix * 256 + offset) - x
                    py = (iy * 256 + offset) - y
                    
                    img = await self.fetch_tile(session, ix, iy, palette, site_name)
                    
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
                            print(f"❌ Paste error [{ix},{iy}]: {e}")
            
            tasks = []
            for iy in range(yc_start, yc_end + 1):
                for ix in range(xc_start, xc_end + 1):
                    tasks.append(fetch_and_paste(ix, iy))
            
            await asyncio.gather(*tasks)
        
        return result


async def handle_chunk_download(message: Message, downloader: ChunkDownloader):
    """Обробляє повідомлення з посиланням на pixel сайт"""
    # Перевіряємо чи є посилання на pixel сайт
    link_data = downloader.detect_pixel_link(message.text or "")
    
    if not link_data:
        return False
    
    site_name, x, y, zoom = link_data
    
    try:
        # Відправляємо повідомлення про завантаження
        loading_msg = await message.answer(
            f"🔄 Завантажую чанк з <b>{site_name}</b> на <code>{x}, {y}</code> (zoom: {zoom})...",
            parse_mode="HTML"
        )
        
        # Завантажуємо область
        image, error = await downloader.download_chunk_area(site_name, x, y, zoom)
        
        if error:
            await loading_msg.edit_text(f"❌ Помилка: {error}")
            return True
        
        if image:
            # Зберігаємо в буфер
            buffer = io.BytesIO()
            image.save(buffer, format='PNG')
            buffer.seek(0)
            
            # Створюємо caption
            caption = (
                f"🗺️ <b>Чанк з {site_name}</b>\n\n"
                f"📍 <b>Координати:</b> <code>{x}, {y}</code>\n"
                f"🔍 <b>Zoom:</b> <code>{zoom}</code>\n"
                f"🔗 <b>Посилання:</b> {SITES[site_name]['url']}#d,{x},{y},{zoom}"
            )
            
            # Відправляємо фото
            photo = BufferedInputFile(buffer.getvalue(), filename="chunk.png")
            await message.answer_photo(
                photo=photo,
                caption=caption,
                parse_mode="HTML"
            )
            
            # Видаляємо повідомлення про завантаження
            await loading_msg.delete()
            
        return True
            
    except Exception as e:
        await message.answer(f"❌ Не вдалося завантажити чанк: {e}")
        return True
    
    return False
