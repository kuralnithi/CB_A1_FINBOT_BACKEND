---
title: "FinBot — Advanced RAG System"
emoji: "🤖"
colorFrom: "blue"
colorTo: "indigo"
sdk: "docker"
app_port: 7860
pinned: true
---

# FinBot — Advanced RAG Backend

This is the FastAPI backend for the FinBot RAG system, designed for deployment on Hugging Face Spaces using Docker.

## Required Environment Variables (HF Secrets)

Set these in your Hugging Face Space settings:

| Variable | Description | Recommendation |
| --- | --- | --- |
| `GROQ_API_KEY` | Groq LLM API Key | Get from [Groq Console](https://console.groq.com/) |
| `DATABASE_URL` | PostgreSQL connection string | Use a managed provider like [Neon.tech](https://neon.tech/) |
| `QDRANT_HOST` | Managed Qdrant Host | Use [Qdrant Cloud](https://cloud.qdrant.io/) for persistent storage |
| `QDRANT_API_KEY` | Managed Qdrant API Key | |
| `SECRET_KEY` | JWT Secret | Run `openssl rand -hex 32` to generate |

## Deployment Note

Hugging Face Spaces are ephemeral by default. For production-grade persistence, ensure your `DATABASE_URL` and `QDRANT_HOST` point to **external managed services**. Avoid local SQLite or local Qdrant for this deployment model.
