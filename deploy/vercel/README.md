# Vercel deployment (experimental, not maintained)

These files are a snapshot of an earlier serverless attempt. They are **not** wired into the main
`docker compose` workflow and have not been re-verified after the backend refactor.

Known limitations on Vercel:

- SQLite and ChromaDB live in `/tmp` and are **not persistent**. The optional Vercel Blob integration
  (`BLOB_READ_WRITE_TOKEN`, see `docs/vercel-blob-storage.md`) syncs the DB/vector store, but it is a
  workaround, not a real database.
- Vercel requires `vercel.json` and `package.json` at the repository root: copy them (and
  `index.py`, plus a root-level `requirements.txt` containing `-r backend/requirements.txt`) there
  and adjust the paths before deploying.

For anything beyond a demo, use the Docker setup in the main README.
