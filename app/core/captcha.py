"""图形验证码：生成 + Redis 存储 + 校验。"""

from __future__ import annotations

import random
import string
import uuid
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from app.core.config import settings
from app.core.logging_setup import get_logger

_log = get_logger(__name__)

_CHARS = string.ascii_uppercase + string.digits
_CAPTCHA_LENGTH = 4
_WIDTH, _HEIGHT = 120, 40
_TTL_SECONDS = 300


def _get_redis():
    import redis as _redis
    return _redis.from_url(settings.redis_url, decode_responses=True)


def _generate_text(length: int = _CAPTCHA_LENGTH) -> str:
    chars = [c for c in _CHARS if c not in 'O0I1L']
    return ''.join(random.choices(chars, k=length))


def _render_image(text: str) -> bytes:
    img = Image.new('RGB', (_WIDTH, _HEIGHT), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype('arial.ttf', 28)
    except (OSError, IOError):
        font = ImageFont.load_default()

    # 干扰线
    for _ in range(4):
        x1, y1 = random.randint(0, _WIDTH), random.randint(0, _HEIGHT)
        x2, y2 = random.randint(0, _WIDTH), random.randint(0, _HEIGHT)
        color = (random.randint(100, 200), random.randint(100, 200), random.randint(100, 200))
        draw.line([(x1, y1), (x2, y2)], fill=color, width=1)

    # 干扰点
    for _ in range(50):
        x, y = random.randint(0, _WIDTH - 1), random.randint(0, _HEIGHT - 1)
        draw.point((x, y), fill=(random.randint(0, 180), random.randint(0, 180), random.randint(0, 180)))

    # 绘制字符
    x_offset = 10
    for ch in text:
        color = (random.randint(20, 100), random.randint(20, 100), random.randint(20, 100))
        draw.text((x_offset, random.randint(2, 8)), ch, font=font, fill=color)
        x_offset += 26

    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def create_captcha() -> tuple[str, bytes]:
    """生成验证码，返回 (captcha_id, png_bytes)。答案存入 Redis，TTL 5 分钟。"""
    captcha_id = str(uuid.uuid4())
    text = _generate_text()
    image_bytes = _render_image(text)

    r = _get_redis()
    r.setex(f'captcha:{captcha_id}', _TTL_SECONDS, text.upper())
    _log.info(f'验证码已生成 id={captcha_id}')
    return captcha_id, image_bytes


def verify_captcha(captcha_id: str, user_input: str) -> bool:
    """校验验证码，使用后立即删除（一次性）。"""
    if not captcha_id or not user_input:
        return False
    r = _get_redis()
    key = f'captcha:{captcha_id}'
    stored = r.get(key)
    if stored is None:
        return False
    r.delete(key)
    return stored.upper() == user_input.strip().upper()
