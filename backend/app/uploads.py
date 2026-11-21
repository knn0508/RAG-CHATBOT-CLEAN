"""Upload validation: extension whitelist, size limit, safe filename."""
import os
from typing import Optional, Tuple

from flask import jsonify
from werkzeug.utils import secure_filename

from config import get_config


def validate_upload(file) -> Tuple[Optional[str], Optional[tuple]]:
    """Validate a werkzeug ``FileStorage``.

    Returns ``(safe_filename, None)`` on success or ``(None, (response, status))``
    on failure so callers can ``return`` the error directly.
    """
    cfg = get_config()
    filename = secure_filename(file.filename or "")
    if not filename:
        return None, (jsonify({"error": "Yanlış fayl adı"}), 400)

    ext = os.path.splitext(filename)[1].lower()
    if ext not in cfg.SUPPORTED_EXTENSIONS:
        allowed = ", ".join(cfg.SUPPORTED_EXTENSIONS)
        return None, (jsonify({"error": f"Dəstəklənməyən fayl tipi. Dəstəklənənlər: {allowed}"}), 400)

    file.stream.seek(0, os.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)
    if size == 0:
        return None, (jsonify({"error": "Fayl boşdur"}), 400)
    if size > cfg.MAX_FILE_SIZE:
        limit_mb = cfg.MAX_FILE_SIZE // (1024 * 1024)
        return None, (jsonify({"error": f"Fayl çox böyükdür (maksimum {limit_mb} MB)"}), 413)

    return filename, None
