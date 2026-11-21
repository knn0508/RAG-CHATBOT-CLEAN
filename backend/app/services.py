"""Service wiring: builds the DB manager, RAG service, chat service and blob storage."""
import logging
import os

from services.blob_storage_service import BlobStorageService
from services.contact_db_search import enhance_rag_with_contact_search
from services.enhanced_chat_service import EnhancedChatService
from services.enhanced_rag_service import EnhancedRAGServiceV2
from services.hr_questions_handler import integrate_hr_handler
from utils.database import DatabaseManager

logger = logging.getLogger(__name__)

_CONTACTS_BLOB_KEY = "_system/contacts.db"


def _sync_blob_state(blob_storage, config) -> None:
    """Restore/push persisted state when Vercel Blob storage is enabled."""
    if not blob_storage.blob_enabled:
        return
    logger.info("Restoring database from Blob Storage")
    blob_storage.sync_db_from_blob(config.DATABASE_FILE)
    contacts_path = config.CONTACTS_DB_FILE
    if config.IS_VERCEL:
        if not os.path.exists("/tmp/contacts.db"):
            blob_storage.sync_file_from_blob(_CONTACTS_BLOB_KEY, "/tmp/contacts.db")
    elif os.path.exists(contacts_path):
        blob_storage.sync_file_to_blob(contacts_path, _CONTACTS_BLOB_KEY)


def init_services(app, config, rag_overrides=None) -> dict:
    """Create all services and attach them to ``app.extensions['rag_services']``.

    ``rag_overrides`` (``openai_client`` / ``embeddings``) lets tests inject fakes.
    """
    os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(config.VECTOR_DB_PATH, exist_ok=True)

    blob_storage = BlobStorageService(config)
    logger.info("Blob storage enabled: %s", blob_storage.blob_enabled)
    _sync_blob_state(blob_storage, config)

    db_manager = DatabaseManager(config.DATABASE_FILE)
    rag_service = EnhancedRAGServiceV2(config, db_manager, **(rag_overrides or {}))
    rag_service.blob_storage = blob_storage  # used for ChromaDB persistence on Vercel
    rag_service = enhance_rag_with_contact_search(rag_service)
    if not hasattr(rag_service, "blob_storage"):
        rag_service.blob_storage = blob_storage

    chat_service = EnhancedChatService(db_manager, rag_service, config)
    integrate_hr_handler(app, db_manager, rag_service, chat_service)

    services = {
        "db_manager": db_manager,
        "rag_service": rag_service,
        "chat_service": chat_service,
        "blob_storage": blob_storage,
    }
    app.extensions["rag_services"] = services
    app.extensions["blob_storage"] = blob_storage
    return services
