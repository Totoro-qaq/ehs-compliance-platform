"""上传策略：扩展名白名单、magic byte 校验与安全存储路径。"""

from __future__ import annotations

import re
import uuid
from datetime import date
from pathlib import Path

from app.core.exceptions import EHSException

# 勘测报告与纯文本场景（Worker 对非 PDF 按 UTF-8 读取正文）
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({'.pdf', '.txt', '.doc', '.docx', '.csv'})

# 文件头 magic bytes 校验表（扩展名 → 合法的文件头前缀列表）
_MAGIC_BYTES: dict[str, list[bytes]] = {
    '.pdf': [b'%PDF'],
    '.doc': [b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'],  # OLE2 Compound Document
    '.docx': [b'PK\x03\x04'],  # ZIP (OOXML)
    # .txt 和 .csv 无固定 magic，跳过检查
}


def validate_original_filename(filename: str | None) -> str:
    """
    校验原始文件名并返回规范化扩展名（小写，含点，如 .pdf）。
    """
    if not filename or not filename.strip():
        raise EHSException('文件名不能为空', code='INVALID_UPLOAD_FILENAME', status_code=400)

    name = Path(filename).name
    if name != filename or '..' in filename or '/' in filename or '\\' in filename:
        raise EHSException('文件名不合法', code='INVALID_UPLOAD_FILENAME', status_code=400)

    suffix = Path(name).suffix.lower()
    if not suffix:
        raise EHSException(
            '文件缺少扩展名，仅支持 PDF、TXT、Word、CSV',
            code='INVALID_UPLOAD_EXTENSION',
            status_code=400,
        )
    if suffix not in ALLOWED_EXTENSIONS:
        raise EHSException(
            f'不支持的文件类型，仅允许：{", ".join(sorted(ALLOWED_EXTENSIONS))}',
            code='INVALID_UPLOAD_EXTENSION',
            status_code=400,
        )
    return suffix


def validate_file_magic(file_bytes: bytes, extension: str) -> None:
    """
    校验文件内容的 magic bytes 是否与声明的扩展名一致，防止扩展名伪造。
    对无固定 magic 的格式（.txt/.csv）跳过。
    """
    expected = _MAGIC_BYTES.get(extension)
    if expected is None:
        return
    header = file_bytes[:8]
    if not any(header.startswith(m) for m in expected):
        raise EHSException(
            f'文件内容与扩展名 {extension} 不匹配，请确认文件未损坏或被篡改',
            code='FILE_MAGIC_MISMATCH',
            status_code=400,
        )


def build_unique_storage_path(upload_dir: Path, original_filename: str) -> tuple[Path, str]:
    """
    按日期分目录存储，避免单目录文件过多；返回 (路径对象, 用于展示的原文件名)。
    """
    suffix = validate_original_filename(original_filename)
    stem = Path(original_filename).name
    stem = stem[: -len(suffix)] if stem.lower().endswith(suffix) else stem
    stem = stem or 'file'
    safe_stem = re.sub(r'[^\w一-鿿.-]', '_', stem).strip('._') or 'file'
    safe_stem = safe_stem[:120]

    # 按日期分目录：uploads/2026/05/17/uuid_filename.pdf
    today = date.today()
    day_dir = upload_dir / str(today.year) / f'{today.month:02d}' / f'{today.day:02d}'
    day_dir.mkdir(parents=True, exist_ok=True)

    unique_name = f'{uuid.uuid4().hex}_{safe_stem}{suffix}'
    return day_dir / unique_name, Path(original_filename).name
