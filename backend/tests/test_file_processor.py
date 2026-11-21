import json

import docx
import pytest

from services.file_processor import FileProcessor

SAMPLE = "Məzuniyyət müddəti 21 gündür. Demo sənəd."


@pytest.fixture()
def processor():
    return FileProcessor()


def test_extract_txt(tmp_path, processor):
    path = tmp_path / "sample.txt"
    path.write_text(SAMPLE, encoding="utf-8")
    assert "21 gündür" in processor.extract_text(str(path))


def test_extract_docx(tmp_path, processor):
    path = tmp_path / "sample.docx"
    document = docx.Document()
    document.add_paragraph(SAMPLE)
    document.save(path)
    assert "21 gündür" in processor.extract_text(str(path))


def test_extract_json(tmp_path, processor):
    path = tmp_path / "sample.json"
    path.write_text(json.dumps({"note": SAMPLE}, ensure_ascii=False), encoding="utf-8")
    assert "21 gündür" in processor.extract_text(str(path))


def test_extract_pdf(tmp_path, processor):
    stream = b"BT /F1 18 Tf 20 100 Td (Leave policy is 21 days) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        pdf += f"{off:010d} 00000 n \n".encode()
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    path = tmp_path / "sample.pdf"
    path.write_bytes(pdf)
    assert "21 days" in processor.extract_text(str(path))


def test_missing_file_returns_none(processor):
    assert processor.extract_text("does-not-exist.txt") is None


def test_validate_file_rejects_unsupported_extension(processor):
    ok, message = processor.validate_file("malware.exe", 1024)
    assert not ok and message
    assert processor.validate_file("notes.txt", 1024)[0]
