# Invoice ERP — Backend API

FastAPI backend for the Invoice ERP platform.

## Stack
- **Runtime**: Python 3.12 (Docker) / 3.11 (local)
- **Framework**: FastAPI + Uvicorn
- **Database**: PostgreSQL (existing instance on VPS)
- **Email**: Resend
- **File Storage**: Local disk on Hostinger VPS
- **Docs**: Swagger UI (`/docs`) · ReDoc (`/redoc`)

## Environments

| Environment | Branch    | Port  |
|-------------|-----------|-------|
| Staging     | `develop` | 8092  |
| Production  | `main`    | 8091  |

## Local Development

```bash
cp .env.example .env        # fill in your local values
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API available at `http://localhost:8000`
Swagger docs at `http://localhost:8000/docs`

## CI/CD

Push to `develop` → deploys to staging on Hostinger VPS (port 8092)
Push to `main` → deploys to production on Hostinger VPS (port 8091)

Pipeline: quality check → tests → build Docker image → push to ghcr.io → SSH deploy

## Project Structure

```
app/
├── main.py           # FastAPI app entry point
├── core/
│   ├── config.py     # Environment-based settings
│   └── database.py   # SQLAlchemy DB connection
├── api/v1/
│   ├── router.py     # Main API router
│   ├── uploads.py    # File upload endpoints
│   └── notifications.py  # In-app notification endpoints
├── models/           # SQLAlchemy models (coming soon)
├── schemas/          # Pydantic request/response schemas (coming soon)
└── services/
    ├── email.py      # Resend email service
    ├── file_upload.py
    └── notifications.py
```
