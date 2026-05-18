"""密码哈希与校验（bcrypt）。"""

from __future__ import annotations

from passlib.context import CryptContext

_pwd = CryptContext(schemes=['bcrypt'], deprecated='auto')


def hash_password(plain: str) -> str:
    """bcrypt；明文过长时 passlib 会处理，建议密码 ≤72 字节。"""
    return _pwd.hash(plain)


def verify_password(plain: str, password_hash: str) -> bool:
    return _pwd.verify(plain, password_hash)
