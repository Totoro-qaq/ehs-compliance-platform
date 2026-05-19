"""主键与时间有序 ID（UUID v7，字符串 36 位）。标准库实现，无 uuid6 依赖。"""

from __future__ import annotations

import secrets
import time
import uuid


def new_uuid_str() -> str:
    """生成 RFC 9562 UUID v7（48-bit 毫秒时间 + 随机），用于 ORM 主键默认值。"""
    # unix_ts_ms：48 位；与同一毫秒内多次生成无单调递增保证（生产环境高并发可改用序列）
    ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF
    rnd = secrets.randbits(74)
    rand_a = (rnd >> 62) & 0xFFF
    rand_b = rnd & ((1 << 62) - 1)

    b = bytearray(16)
    b[0:6] = ms.to_bytes(6, 'big')
    b[6] = (0x7 << 4) | ((rand_a >> 8) & 0x0F)
    b[7] = rand_a & 0xFF
    b[8] = 0x80 | ((rand_b >> 56) & 0x3F)
    b[9:16] = (rand_b & ((1 << 56) - 1)).to_bytes(7, 'big')

    return str(uuid.UUID(bytes=bytes(b)))
