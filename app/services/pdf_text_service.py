"""Document text extraction helpers for PDF, DOCX, DOC and plain text files."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from pypdf import PdfReader

if TYPE_CHECKING:
    from paddleocr import PaddleOCR

_log = logging.getLogger(__name__)

_WORD_NAMESPACE = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

# PaddleOCR model instance: lazy-loaded and reused per process.
_ocr_engine: PaddleOCR | None = None


class DocumentTextExtractError(Exception):
    """Raised when a supported document cannot be converted into usable text."""


def _get_ocr_engine() -> "PaddleOCR":
    """Initialize PaddleOCR lazily so model loading does not happen at import time."""
    global _ocr_engine
    if _ocr_engine is None:
        from paddleocr import PaddleOCR

        _ocr_engine = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)
    return _ocr_engine


def _extract_text_pypdf(path: Path) -> str:
    """Extract text from the embedded PDF text layer."""
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            parts.append(text)
    return '\n'.join(parts).strip()


def _extract_text_ocr(path: Path) -> str:
    """Convert each PDF page to an image and OCR it with PaddleOCR."""
    from pdf2image import convert_from_path

    images = convert_from_path(str(path), dpi=200)
    ocr = _get_ocr_engine()
    all_text: list[str] = []

    for i, img in enumerate(images):
        import numpy as np

        img_array = np.array(img)
        result = ocr.ocr(img_array, cls=True)
        if not result or not result[0]:
            continue

        page_lines: list[str] = []
        for line in result[0]:
            text = line[1][0]
            if text.strip():
                page_lines.append(text.strip())
        if page_lines:
            all_text.append('\n'.join(page_lines))
        _log.debug('OCR completed page %d/%d', i + 1, len(images))

    return '\n'.join(all_text).strip()


def _extract_text_docx(path: Path) -> str:
    """Extract text from a DOCX package by reading word/document.xml."""
    try:
        with ZipFile(path) as archive:
            xml_bytes = archive.read('word/document.xml')
    except FileNotFoundError as exc:
        raise DocumentTextExtractError(f'DOCX file not found: {path}') from exc
    except KeyError as exc:
        raise DocumentTextExtractError('DOCX is missing word/document.xml') from exc
    except BadZipFile as exc:
        raise DocumentTextExtractError('DOCX package is corrupted or not a valid zip file') from exc

    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as exc:
        raise DocumentTextExtractError('DOCX XML parsing failed') from exc

    paragraphs: list[str] = []
    for paragraph in root.findall('.//w:p', _WORD_NAMESPACE):
        texts = [node.text for node in paragraph.findall('.//w:t', _WORD_NAMESPACE) if node.text]
        line = ''.join(texts).strip()
        if line:
            paragraphs.append(line)
    return '\n'.join(paragraphs).strip()


def _extract_text_doc(path: Path) -> str:
    """
    Extract text from legacy .doc files using antiword.

    We prefer a small external utility here instead of silently decoding binary bytes,
    because that produces unreliable garbage and misrepresents support for .doc files.
    """
    try:
        result = subprocess.run(
            ['antiword', str(path)],
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
        )
    except FileNotFoundError as exc:
        raise DocumentTextExtractError(
            'DOC parsing requires antiword to be installed in the runtime environment'
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or '').strip()
        raise DocumentTextExtractError(
            f'DOC parsing failed via antiword: {stderr or exc.returncode}'
        ) from exc
    return result.stdout.strip()


def _extract_text_plain(path: Path, *, max_chars: int) -> str:
    raw = path.read_bytes()
    return raw.decode('utf-8', errors='ignore')[:max_chars].strip()


# Threshold below which we consider the PDF text layer insufficient and fall back to OCR.
_MIN_TEXT_THRESHOLD = 50


def extract_text_from_pdf_file(file_path: str | Path, *, max_chars: int = 200_000) -> str:
    """
    Extract PDF text: try the embedded text layer first, then OCR when text is sparse.
    """
    path = Path(file_path)
    if not path.is_file():
        raise DocumentTextExtractError(f'File does not exist: {path}')
    try:
        text = _extract_text_pypdf(path)
        if len(text) < _MIN_TEXT_THRESHOLD:
            _log.info('PDF text layer too short (%d chars), falling back to OCR: %s', len(text), path.name)
            text = _extract_text_ocr(path)

        if not text:
            _log.warning('PDF extraction produced no text after text-layer and OCR attempts: %s', path.name)

        if len(text) > max_chars:
            text = text[:max_chars]
        return text
    except DocumentTextExtractError:
        raise
    except Exception as exc:
        raise DocumentTextExtractError(f'PDF parsing failed: {exc}') from exc


def extract_text_from_document_file(file_path: str | Path, *, max_chars: int = 200_000) -> str:
    """Extract text from a supported document format based on file extension."""
    path = Path(file_path)
    if not path.is_file():
        raise DocumentTextExtractError(f'File does not exist: {path}')

    suffix = path.suffix.lower()
    try:
        if suffix == '.pdf':
            text = extract_text_from_pdf_file(path, max_chars=max_chars)
        elif suffix == '.docx':
            text = _extract_text_docx(path)
        elif suffix == '.doc':
            text = _extract_text_doc(path)
        else:
            text = _extract_text_plain(path, max_chars=max_chars)
    except DocumentTextExtractError:
        raise
    except Exception as exc:
        raise DocumentTextExtractError(f'{suffix or "document"} parsing failed: {exc}') from exc

    text = text.strip()
    if len(text) > max_chars:
        text = text[:max_chars]
    return text
