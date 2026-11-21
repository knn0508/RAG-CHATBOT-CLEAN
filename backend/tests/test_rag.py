"""Chunking + retrieval with fake embeddings (no network)."""
import sys

import pytest

from config import get_config


def _service(app):
    return app.extensions["rag_services"]["rag_service"]


def _insert_doc(app, path, name="policy.txt"):
    db = app.extensions["rag_services"]["db_manager"]
    return db.create_document(
        filename=name, original_name=name, file_path=str(path), file_size=path.stat().st_size,
        file_type="TXT", uploaded_by=1,
    )


def test_long_text_is_split_into_overlapping_chunks(app, tmp_path):
    rag = _service(app)
    text = ". ".join(f"Sentence number {i} about leave policy" for i in range(200))
    chunks = rag.text_splitter.split_text(text)
    assert len(chunks) > 1
    assert all(len(c) <= get_config().CHUNK_SIZE for c in chunks)


def test_retrieval_returns_relevant_chunk(app, tmp_path):
    rag = _service(app)
    path = tmp_path / "policy.txt"
    path.write_text(
        "Vacation lasts 21 calendar days.\n\n" + "Unrelated filler about office parking rules. " * 80
        + "\n\nSick leave certificates are due within 2 working days.",
        encoding="utf-8",
    )
    doc_id = _insert_doc(app, path)
    assert rag.process_document(str(path), doc_id) is True

    context = rag.search_relevant_content("How long does vacation last?", doc_id)
    assert context and "21 calendar days" in context


@pytest.mark.skipif(sys.platform == "win32", reason="Chroma keeps index files locked on Windows")
def test_delete_vectors_removes_index(app, tmp_path):
    rag = _service(app)
    path = tmp_path / "policy.txt"
    path.write_text("Vacation lasts 21 calendar days.", encoding="utf-8")
    doc_id = _insert_doc(app, path)
    rag.process_document(str(path), doc_id)
    rag.delete_document_vectors(doc_id)
    assert not rag.search_relevant_content("vacation", doc_id)
