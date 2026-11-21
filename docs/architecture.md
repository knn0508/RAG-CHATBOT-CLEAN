# Architecture notes

```
backend/
  wsgi.py                 entrypoint (gunicorn wsgi:app)
  app/
    __init__.py           create_app() factory: config, CORS, sessions, error handlers, blueprints
    auth.py               JWT + session decorators (login_required / admin_required)
    extensions.py         lazy proxies (db_manager, rag_service, chat_service, blob_storage)
    services.py           builds and wires services onto app.extensions
    uploads.py            upload validation (extension whitelist, size, safe filename)
    blueprints/           auth, chat, documents, admin, health
  services/               RAG, chat orchestration, document matching, keyword extraction, contact search
  utils/database.py       SQLite access layer
  config.py               single env-driven configuration object
  scripts/seed_demo_data.py
```

There is no separate `contacts` blueprint: contact lookups are answered through the chat endpoint
(see below), and the old standalone contact routes were never registered.

## Request flow for a chat question

1. `POST /api/chat/ask` -> `chat.ask_question`.
2. If `document_id` is given, the RAG service answers from that document directly.
3. Otherwise `EnhancedChatService.process_chat_message` decides: template/file request, HR question,
   document question (best matching document by keywords/name) or general question.
4. Conversations are stored per user in SQLite.

## Contact (phone book) search

`services/contact_db_search.py` wraps the RAG service: questions that look like "who is / phone number of /
people in department X" are answered from a `contacts` SQLite table (`CONTACTS_DB_FILE`) instead of the
vector store. Columns: `Ad, Soyad, Vəzifə, Şöbə, Sektor, Mobil, Daxili, Şəhər, Email`.
`python scripts/seed_demo_data.py` creates a table with 30 fictional people. Lookups work by name, by
department (`Şöbə`) and by sector (`Sektor`), and the e-mail is returned when present.

## Vercel Blob storage (optional)

`services/blob_storage_service.py` is only active when a Blob token is set. See `docs/vercel.md`.
