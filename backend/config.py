"""Application configuration (single source of truth, driven by environment variables)."""
import logging
import os
import secrets

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _list(name: str, default: str) -> list:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


class Config:
    """Configuration object. Values are read from the environment when instantiated."""

    SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md", ".json", ".xlsx", ".xls")

    def __init__(self) -> None:
        self.ENV = os.getenv("FLASK_ENV", "development").lower()
        self.IS_PRODUCTION = self.ENV == "production"
        self.IS_VERCEL = os.getenv("VERCEL", "") == "1"
        self.DEBUG = _bool("DEBUG", False)

        # --- Secrets -----------------------------------------------------
        self.SECRET_KEY = self._secret("SECRET_KEY")
        self.JWT_SECRET_KEY = self._secret("JWT_SECRET_KEY", fallback=self.SECRET_KEY)
        self.JWT_EXPIRES_HOURS = int(os.getenv("JWT_EXPIRES_HOURS", 24))

        # --- Cookies -----------------------------------------------------
        self.COOKIE_SECURE = _bool("COOKIE_SECURE", self.IS_PRODUCTION)
        self.COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "None" if self.COOKIE_SECURE else "Lax")

        # --- CORS --------------------------------------------------------
        self.CORS_ORIGINS = _list("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")

        # --- Storage (on Vercel only /tmp is writable) ---------------------
        tmp = "/tmp/" if self.IS_VERCEL else ""
        self.DATABASE_FILE = os.getenv("DATABASE_FILE", f"{tmp}rag_chatbot.db")
        self.CONTACTS_DB_FILE = os.getenv("CONTACTS_DB_FILE", "contacts.db")
        self.UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", f"{tmp}documents")
        self.VECTOR_DB_PATH = os.getenv("VECTOR_DB_PATH", f"{tmp}chroma_db")
        self.EXAMPLE_DOCS_DIR = os.getenv(
            "EXAMPLE_DOCS_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "example_docs")
        )
        self.MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 10 * 1024 * 1024))

        # --- AI ----------------------------------------------------------
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
        self.LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        self.CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 1000))
        self.CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 200))
        self.SEARCH_RESULTS_COUNT = int(os.getenv("SEARCH_RESULTS_COUNT", 5))

    def _secret(self, name: str, fallback: str = "") -> str:
        value = os.getenv(name) or fallback
        if value:
            return value
        if self.IS_PRODUCTION:
            raise RuntimeError(f"{name} must be set when FLASK_ENV=production")
        logger.warning(
            "%s is not set; using a random per-process key (sessions/tokens reset on restart). "
            "Set it in .env for stable development sessions.",
            name,
        )
        return secrets.token_hex(32)


_config = None


def get_config() -> Config:
    """Return the process-wide configuration (created on first use)."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def reset_config() -> None:
    """Drop the cached configuration (used by tests)."""
    global _config
    _config = None
