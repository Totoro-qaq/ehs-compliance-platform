from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from app.services.pdf_text_service import (
    DocumentTextExtractError,
    extract_text_from_document_file,
    extract_text_from_pdf_file,
)


def test_extract_text_from_docx_file(tmp_path: Path):
    docx_path = tmp_path / 'sample.docx'
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>'
        '<w:p><w:r><w:t>First line</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>Second line</w:t></w:r></w:p>'
        '</w:body>'
        '</w:document>'
    )
    with ZipFile(docx_path, 'w') as archive:
        archive.writestr('word/document.xml', xml)

    text = extract_text_from_document_file(docx_path)

    assert text == 'First line\nSecond line'


def test_extract_text_from_doc_uses_antiword(tmp_path: Path):
    doc_path = tmp_path / 'sample.doc'
    doc_path.write_bytes(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1fake-doc')

    class _Result:
        stdout = 'Legacy DOC text'

    with patch('app.services.pdf_text_service.subprocess.run', return_value=_Result()) as run_mock:
        text = extract_text_from_document_file(doc_path)

    assert text == 'Legacy DOC text'
    run_mock.assert_called_once()


def test_extract_text_from_doc_raises_when_antiword_missing(tmp_path: Path):
    doc_path = tmp_path / 'sample.doc'
    doc_path.write_bytes(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1fake-doc')

    with patch('app.services.pdf_text_service.subprocess.run', side_effect=FileNotFoundError()):
        try:
            extract_text_from_document_file(doc_path)
            raise AssertionError('expected DocumentTextExtractError')
        except DocumentTextExtractError as exc:
            assert 'antiword' in str(exc)


def test_pdf_ocr_disabled_does_not_call_ocr(monkeypatch, tmp_path: Path):
    pdf_path = tmp_path / 'scan.pdf'
    pdf_path.write_bytes(b'%PDF-1.7 fake scanned pdf')
    monkeypatch.setattr('app.services.pdf_text_service.settings.pdf_ocr_enabled', False)
    monkeypatch.setattr('app.services.pdf_text_service._extract_text_pypdf', lambda _path: '')

    def _fail_ocr(_path):
        raise AssertionError('OCR should not be called when disabled')

    monkeypatch.setattr('app.services.pdf_text_service._extract_text_ocr', _fail_ocr)

    assert extract_text_from_pdf_file(pdf_path) == ''
