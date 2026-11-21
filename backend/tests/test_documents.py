import io

LEAVE_TEXT = "Illik əsas məzuniyyət 21 təqvim günüdür. Məzuniyyət ərizəsi 10 iş günü əvvəl verilir."


def _upload(client, headers, name="leave.txt", content=None, **extra):
    content = LEAVE_TEXT.encode("utf-8") if content is None else content
    data = {"file": (io.BytesIO(content), name), "document_type": "vacation", **extra}
    return client.post("/api/documents", data=data, headers=headers, content_type="multipart/form-data")


def test_upload_requires_admin(client, user_headers):
    assert _upload(client, user_headers).status_code == 403


def test_upload_requires_auth(client):
    assert _upload(client, {}).status_code == 401


def test_upload_and_list_document(client, admin_headers):
    resp = _upload(client, admin_headers)
    assert resp.status_code == 201
    body = resp.get_json()["document"]
    assert body["is_processed"] is True
    assert body["type"] == "TXT"

    listing = client.get("/api/documents", headers=admin_headers).get_json()["documents"]
    assert [d["name"] for d in listing] == ["leave.txt"]


def test_upload_rejects_unsupported_extension(client, admin_headers):
    resp = _upload(client, admin_headers, name="payload.exe", content=b"MZ")
    assert resp.status_code == 400


def test_upload_rejects_empty_file(client, admin_headers):
    assert _upload(client, admin_headers, content=b"").status_code == 400


def test_upload_rejects_oversized_file(client, admin_headers):
    resp = _upload(client, admin_headers, content=b"a" * (60 * 1024))
    assert resp.status_code == 413


def test_upload_sanitises_path_traversal(client, admin_headers, app):
    resp = _upload(client, admin_headers, name="../../evil.txt")
    assert resp.status_code == 201
    assert resp.get_json()["document"]["name"] == "evil.txt"


def test_delete_document(client, admin_headers):
    doc_id = _upload(client, admin_headers).get_json()["document"]["id"]
    assert client.delete(f"/api/documents/{doc_id}", headers=admin_headers).status_code == 200
    assert client.get("/api/documents", headers=admin_headers).get_json()["documents"] == []
