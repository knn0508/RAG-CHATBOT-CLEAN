# Known limitations

- SQLite + a single Chroma persistent client: run **one** gunicorn worker (threads are fine).
- Intent routing (HR / template / contact / document) is keyword based, tuned for Azerbaijani text.
- The Azerbaijani UI strings are hard-coded (no i18n layer).
- The frontend still has a few `react-hooks/exhaustive-deps` warnings.
- No rate limiting, no password reset, no e-mail verification.
- Legacy service code still contains broad `except:` blocks (ruff rule E722 is ignored for now).
- `langchain_community.vectorstores.Chroma` is deprecated; migrate to `langchain-chroma`.
- Chroma index files stay locked on Windows, so deleting a document's vectors can fail there (works on Linux/Docker).
- The default `LLM_MODEL` is now `gpt-4o-mini` (the previous default `gpt-5.2` could not be verified).
