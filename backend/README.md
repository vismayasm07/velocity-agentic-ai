# Velocity CRM Backend

FastAPI backend for the Velocity CRM Agent.

## Local services

PostgreSQL 17 is installed as a project-local runtime and configured with:

- Database: `velocity`
- Application role: `velocity_app`
- Port: `5432`

The operational policy knowledge base requires the pgvector server extension.
The local runtime currently uses pgvector `0.8.6`; enable the extension in each
new database as its owner before applying migrations:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Start PostgreSQL after restarting Windows:

```powershell
& .\scripts\start-postgres.ps1
```

Stop it with:

```powershell
& .\scripts\stop-postgres.ps1
```

## Run locally

```powershell
& .\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the OpenAPI UI. Use `/health/live`
for process health and `/health/ready` to verify the `velocity` PostgreSQL
database connection.

## Database migrations

Apply pending schema migrations before starting the API:

```powershell
& .\.venv\Scripts\python.exe -m alembic upgrade head
```

The application seeds a default local admin at startup when the configured
email does not exist. Development credentials are configured in the ignored
`.env` file:

- Email: `admin@velocitycrm.com`
- Password: `VelocityAdmin@2026`

Change `ADMIN_PASSWORD` outside local development. PostgreSQL stores only the
Argon2 password hash, never the plaintext password.

## Knowledge embeddings

Startup idempotently seeds five operational policy documents and their vector
chunks. Development and tests default to a deterministic local 768-dimensional
embedder, so no external credentials are required. To use Google embeddings,
configure:

```dotenv
EMBEDDING_PROVIDER=google
GOOGLE_API_KEY=your-key
GOOGLE_EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSIONS=768
```

The authenticated knowledge API exposes `GET /api/knowledge/documents` and
`POST /api/knowledge/search`. The search body accepts `query`, optional
`incident_type`, and `limit` from 1 through 20.

## Gemini root cause analysis

Configure the read-only incident analysis provider in the ignored `.env` file:

```dotenv
GEMINI_API_KEY=your-google-ai-studio-key
GEMINI_MODEL=your-supported-gemini-model
GEMINI_TEMPERATURE=0.2
```

`POST /api/incidents/{incident_id}/analyze` retrieves relevant policy chunks,
requests a structured Gemini analysis, validates its controlled action and
policy references, and persists the result with sanitized provider telemetry.
`GET /api/incidents/{incident_id}/analysis` returns the latest completed or
failed state. Both endpoints require a bearer token. Failed attempts may be
retried; recommendations are read-only and never execute CRM writes.

## Zoho CRM integration

The local/demo CRM adapter remains the default. Configure `CRM_ADAPTER=zoho`
only after an administrator has connected Zoho and granted the configured
minimum scopes. OAuth tokens are stored encrypted and are never returned by the
API. Generate `ZOHO_TOKEN_ENCRYPTION_KEY` as a Fernet key and keep it outside
source control.

The integration supports paginated Deal retrieval and synchronization, Zoho
Task creation for governed follow-ups, and approved Deal owner reassignment.
Use `GET /api/integrations/zoho/status` for connection and sync metadata,
`POST /api/integrations/zoho/test` to verify access, and
`DELETE /api/integrations/zoho` to revoke and remove the connection.