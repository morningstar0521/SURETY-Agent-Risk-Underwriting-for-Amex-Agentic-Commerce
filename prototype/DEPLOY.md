# Deploying the SURETY policy service

The service is a single stateless FastAPI process with no database and no
external dependencies, so every free-tier host below works without changes.

The audit ledger is in-memory: it resets when the instance restarts or sleeps.
That is fine for a demo, and it is the honest Round 1 scope. Round 2 moves the
ledger to PostgreSQL.

---

## Option 1 — Render (recommended, free)

A blueprint is committed at [`../render.yaml`](../render.yaml).

1. Push this repository to GitHub.
2. Open <https://dashboard.render.com/blueprints> → **New Blueprint Instance**.
3. Select the repository. Render reads `render.yaml` and deploys.
4. You get a URL like `https://surety-policy-service.onrender.com`.

No card required. Free instances sleep after 15 minutes idle and take about
30 seconds to wake, so **hit the URL once a few minutes before any demo**.

Manual setup instead of the blueprint:

| Setting | Value |
|---|---|
| Root directory | `prototype` |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/health` |

---

## Option 2 — Railway (free trial credit)

```bash
npm i -g @railway/cli
railway login
cd prototype
railway init
railway up
```

Railway detects the `Dockerfile` and builds it. Set no environment variables;
`PORT` is injected automatically.

---

## Option 3 — Fly.io (free allowance)

```bash
cd prototype
fly launch --now          # detects the Dockerfile, pick a region near you
```

---

## Option 4 — Hugging Face Spaces (free, no card, never sleeps on CPU basic)

1. Create a Space, SDK **Docker**.
2. Upload `Dockerfile`, `main.py`, `requirements.txt` and `static/`.
3. Spaces expose port 7860, so change the last line of the Dockerfile to:

```dockerfile
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
```

---

## Option 5 — Docker anywhere

```bash
cd prototype
docker build -t surety .
docker run -p 8000:8000 surety
# http://127.0.0.1:8000
```

---

## After deploying

Smoke-test the live URL:

```bash
BASE=https://your-app.onrender.com

curl -s $BASE/health

curl -s -X POST $BASE/evaluate \
  -H 'Content-Type: application/json' \
  -d '{"agent_id":"shop-bot-7","transaction_amount":42000,"exposure_limit":15000,"risk_score":0.78,"risk_tier":"BRONZE"}'

curl -s $BASE/audit/verify
```

Then put the live URL in the repository README and in the submission form. A
judge who can click a link and see the console decide a transaction is worth
more than any screenshot.

---

## Notes for production

Out of scope for Round 1, listed so the gap is explicit:

- The audit ledger must move to PostgreSQL for durability.
- `/evaluate` should require authentication; it is currently open.
- CORS is unrestricted because the console is served from the same origin.
- Rate limiting and request-size caps belong at the gateway.
