import io

LEAVE_TEXT = "Illik əsas məzuniyyət 21 təqvim günüdür. Məzuniyyət ərizəsi 10 iş günü əvvəl verilir."


def _upload_doc(client, headers):
    data = {"file": (io.BytesIO(LEAVE_TEXT.encode("utf-8")), "leave.txt"), "document_type": "vacation"}
    resp = client.post("/api/documents", data=data, headers=headers, content_type="multipart/form-data")
    assert resp.status_code == 201
    return resp.get_json()["document"]["id"]


def test_chat_requires_auth(client):
    assert client.post("/api/chat/ask", json={"question": "hi"}).status_code == 401


def test_chat_requires_question(client, user_headers):
    assert client.post("/api/chat/ask", json={"question": "  "}, headers=user_headers).status_code == 400


def test_chat_unknown_document(client, user_headers):
    resp = client.post("/api/chat/ask", json={"question": "hello", "document_id": 999}, headers=user_headers)
    assert resp.status_code == 404


def test_chat_answers_from_document_with_mocked_llm(client, admin_headers, fake_llm):
    doc_id = _upload_doc(client, admin_headers)

    resp = client.post(
        "/api/chat/ask",
        json={"question": "Məzuniyyət neçə gündür?", "document_id": doc_id},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "FAKE LLM ANSWER" in body["answer"]
    assert body["document_used"]["id"] == doc_id
    assert body["conversation_id"]

    # retrieval fed the document text into the prompt sent to the (fake) LLM
    assert fake_llm.prompts, "LLM was not called"
    assert "21 təqvim" in fake_llm.prompts[-1]


def test_conversation_is_persisted_per_user(client, admin_headers, user_headers):
    doc_id = _upload_doc(client, admin_headers)
    resp = client.post(
        "/api/chat/ask", json={"question": "Məzuniyyət neçə gündür?", "document_id": doc_id}, headers=admin_headers
    )
    conv_id = resp.get_json()["conversation_id"]

    own = client.get("/api/chat/conversations", headers=admin_headers).get_json()["conversations"]
    assert [c["id"] for c in own] == [conv_id]
    assert client.get("/api/chat/conversations", headers=user_headers).get_json()["conversations"] == []
    assert client.get(f"/api/chat/conversations/{conv_id}", headers=user_headers).status_code == 404
