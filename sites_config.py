# sites_config.py
"""
Конфігурація pixel-art сайтів для бота
"""

SITES = {
    "pixelya": {
        "url": "https://pixelya.fun",
        "api_me": "https://pixelya.fun/api/me",
        "api_ranking": "https://pixelya.fun/api/ranking",
        "chunk_url": "https://pixelya.fun/tiles/5/{x}/{y}.bin",
        "void_url": "https://pixelya.fun/void",
        "canvas_id": "5",
        "link_pattern": r"pixelya\.fun/#d,(-?\d+),(-?\d+),(\d+)"
    },
    "pixunivers": {
        "url": "https://pixunivers.fun",
        "api_me": "https://pixunivers.fun/api/me",
        "api_ranking": "https://pixunivers.fun/api/ranking",
        "chunk_url": "https://pixunivers.fun/tiles/0/{x}/{y}.bin",
        "void_url": "https://pixunivers.fun/void",
        "canvas_id": "0",
        "link_pattern": r"pixunivers\.fun/#d,(-?\d+),(-?\d+),(\d+)"
    }
}


def get_site_names():
    """Повертає список доступних сайтів"""
    return list(SITES.keys())


def is_valid_site(site_name):
    """Перевіряє чи існує сайт в конфігурації"""
    return site_name in SITES


def get_site_config(site_name):
    """Отримує конфігурацію сайту"""
    return SITES.get(site_name)
