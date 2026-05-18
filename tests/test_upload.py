"""Upload validation tests: extension whitelist, magic bytes and filename safety."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


class TestUploadValidation:
    def _upload(
        self,
        client: TestClient,
        token: str,
        filename: str,
        content: bytes,
        content_type: str = 'application/octet-stream',
    ):
        return client.post(
            '/api/v1/assessment',
            files={'file': (filename, content, content_type)},
            headers={'Authorization': f'Bearer {token}'},
        )

    def test_reject_disallowed_extension(self, client: TestClient, admin_token: str):
        resp = self._upload(client, admin_token, 'malware.exe', b'MZ\x90\x00')
        assert resp.status_code == 400
        assert resp.json()['code'] == 'INVALID_UPLOAD_EXTENSION'

    def test_reject_no_extension(self, client: TestClient, admin_token: str):
        resp = self._upload(client, admin_token, 'noext', b'some content')
        assert resp.status_code == 400
        assert resp.json()['code'] == 'INVALID_UPLOAD_EXTENSION'

    def test_reject_pdf_magic_mismatch(self, client: TestClient, admin_token: str):
        resp = self._upload(client, admin_token, 'fake.pdf', b'NOT_A_PDF_CONTENT_HERE')
        assert resp.status_code == 400
        assert resp.json()['code'] == 'FILE_MAGIC_MISMATCH'

    def test_reject_docx_magic_mismatch(self, client: TestClient, admin_token: str):
        resp = self._upload(client, admin_token, 'fake.docx', b'plain text not a zip')
        assert resp.status_code == 400
        assert resp.json()['code'] == 'FILE_MAGIC_MISMATCH'

    def test_reject_doc_magic_mismatch(self, client: TestClient, admin_token: str):
        resp = self._upload(client, admin_token, 'fake.doc', b'plain text not an ole2 file')
        assert resp.status_code == 400
        assert resp.json()['code'] == 'FILE_MAGIC_MISMATCH'

    def test_accept_valid_txt(self, client: TestClient, admin_token: str):
        with patch('app.tasks.worker.run_assessment_task.delay', new=MagicMock()):
            resp = self._upload(client, admin_token, 'report.txt', b'EHS compliance report content')
        assert resp.status_code == 200
        data = resp.json()['data']
        assert 'task_id' in data

    def test_accept_valid_pdf(self, client: TestClient, admin_token: str):
        pdf_header = b'%PDF-1.7 fake pdf body for testing'
        with patch('app.tasks.worker.run_assessment_task.delay', new=MagicMock()):
            resp = self._upload(client, admin_token, 'report.pdf', pdf_header)
        assert resp.status_code == 200

    def test_accept_valid_docx(self, client: TestClient, admin_token: str):
        docx_like = b'PK\x03\x04fake-docx-zip'
        with patch('app.tasks.worker.run_assessment_task.delay', new=MagicMock()):
            resp = self._upload(
                client,
                admin_token,
                'report.docx',
                docx_like,
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            )
        assert resp.status_code == 200

    def test_accept_valid_doc(self, client: TestClient, admin_token: str):
        doc_like = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1legacy-doc'
        with patch('app.tasks.worker.run_assessment_task.delay', new=MagicMock()):
            resp = self._upload(client, admin_token, 'report.doc', doc_like, 'application/msword')
        assert resp.status_code == 200

    def test_accept_valid_csv(self, client: TestClient, admin_token: str):
        with patch('app.tasks.worker.run_assessment_task.delay', new=MagicMock()):
            resp = self._upload(client, admin_token, 'data.csv', b'col1,col2\nval1,val2')
        assert resp.status_code == 200

    def test_reject_empty_filename(self, client: TestClient, admin_token: str):
        resp = self._upload(client, admin_token, '', b'content')
        assert resp.status_code in (400, 422, 500)

    def test_reject_directory_traversal(self, client: TestClient, admin_token: str):
        resp = self._upload(client, admin_token, '../../../etc/passwd.txt', b'content')
        assert resp.status_code == 400
        assert resp.json()['code'] == 'INVALID_UPLOAD_FILENAME'
