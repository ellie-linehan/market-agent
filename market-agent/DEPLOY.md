# Deploy

**Architecture:** backend (FastAPI + ADK + Phoenix MCP) → **Google Cloud Run**; frontend (Next.js) → **Vercel**. MongoDB Atlas and Phoenix Cloud are managed/public.

All backend commands run from the `market-agent/` directory (where the `Dockerfile` is).

## Prerequisites
- `gcloud` CLI installed and authed: `gcloud auth login` and `gcloud config set project woven-respect-386818`
- Enable APIs once: `gcloud services enable run.googleapis.com cloudbuild.googleapis.com`
- **MongoDB Atlas → Network Access → add `0.0.0.0/0`** (Cloud Run egress IPs are dynamic).
- Your `.env` values handy (`GOOGLE_API_KEY`, `MONGODB_URI`, `PHOENIX_API_KEY`, `PHOENIX_COLLECTOR_ENDPOINT`).

## 1. Backend → Cloud Run
Builds in the cloud (Cloud Build) — no local Docker needed. The `^##^` delimiter lets values contain commas safely.

```bash
cd market-agent
gcloud run deploy market-agent-api \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi --cpu 2 --timeout 300 \
  --min-instances 1 \
  --set-env-vars "^##^GEMINI_MODEL=gemini-3.5-flash##MONGODB_DATABASE=market_agent##PHOENIX_PROJECT_NAME=market-agent##PHOENIX_COLLECTOR_ENDPOINT=https://app.phoenix.arize.com/s/<your-space>##GOOGLE_API_KEY=<key>##MONGODB_URI=<uri>##PHOENIX_API_KEY=<key>"
```

Notes:
- `--min-instances 1` keeps the Phoenix MCP connection pre-warmed (no cold-start on the demo).
- For real secret hygiene, put `GOOGLE_API_KEY` / `MONGODB_URI` / `PHOENIX_API_KEY` in Secret Manager and use `--set-secrets` instead of `--set-env-vars`.
- Note the service URL it prints (e.g. `https://market-agent-api-xxxx.run.app`).
- Smoke test: `curl https://<service-url>/health` → `{"status":"ok"}`.

## 2. Frontend → Vercel
The frontend only talks to its own `/api/*` routes (which proxy to the backend server-side), so there's no CORS to configure.

1. Import the GitHub repo in Vercel.
2. **Root Directory:** `market-agent/frontend`.
3. **Environment variable:** `FASTAPI_URL = https://<your-cloud-run-url>`.
4. Deploy. Open the Vercel URL — this is your **hosted project URL** for the submission.

## 3. Before submitting
- Make the repo public: `gh repo edit ellie-linehan/market-agent --visibility public --accept-visibility-change-consequences`
- Confirm the demo end-to-end on the hosted URL: analyze a company → grounding badge → keep/dismiss → re-run shows change diff → `/insights` answers from Phoenix.
