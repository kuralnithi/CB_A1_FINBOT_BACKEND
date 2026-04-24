# Changelog

All notable changes to this project will be documented in this file.

## [0.1.1] - 2026-04-24

### Changed
- Changed llm to llama 70b (26124af)
- Readme updated (1cbbf7b)
- Dynamic changes (2e3baa5)

### Fixed
- Ingest: disable Docling OCR and table layout extraction to prevent Railway OOM kill (eb3c77b)
- Ingest: prevent UI zero-state and downtime by clearing Qdrant only after chunking finishes (4168288)
- Isolate Docling in detached subprocess to prevent OS kernel OOM crashes (0aaae65)
- Ingest: move heavy docling vector indexing to background tasks to fix railway 502 timeout (673e032)
- Start script for Railway deployment (5889e5a)
- uv dependency resolution issue for railway (0e9ddb9)
- Dockerfile for railway and ignore env secrets (11ab512)
- Line endings for linux (ff0a32a)

### Other
- Checking git agent (68d7187, 4cfa91f)
- Cred (e454ee8)
- Injestion using run_in_threadpool (f0ef6da)
- Hardcode port 7860, ignore platform overrides (bfab482)
- Changes (9d93eab, d794fed)
- Rag2 to rag (9204fc0)
- Empty cmt (4468555)
