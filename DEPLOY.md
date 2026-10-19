# Deploying the Openhouse backend to Render

Render fits this backend well because web services are regular long-running
processes (not serverless functions), so the WebSocket hub, its background
Redis-listener task, and the async DB connection pool all behave exactly like
they do locally — unlike Vercel's serverless Python runtime, which can't keep
any of that alive between requests.

Render provides managed Postgres and a managed Redis-compatible "Key Value"
store, but **no S3-compatible object storage** — you need that from an
outside provider. [Cloudflare R2](https://developers.cloudflare.com/r2/) is
the easiest fit: S3-compatible API, a free tier, and no egress fees.

## 1. Set up object storage first

Pick one:

- **Cloudflare R2** (recommended): create a bucket, then an R2 API token
  (Account → R2 → Manage API Tokens). You'll end up with:
  - Endpoint URL: `https://<account-id>.r2.cloudflarestorage.com`
  - Bucket name, Access Key ID, Secret Access Key
  - Region: use `auto`
- **AWS S3**: create a bucket + an IAM user scoped to it. Leave the endpoint
  URL blank (AWS S3 uses default endpoint resolution) and set the real
  region (e.g. `us-east-1`).

Keep these four values handy — the blueprint deploy below asks for them.

## 2. Deploy the blueprint

1. Push this repo to GitHub (already done if you're reading this from the
   repo).
2. In the Render dashboard: **New → Blueprint**, connect the
   `William-franklyn/openHouse` repo. Render reads `render.yaml` at the repo
   root automatically.
3. Render provisions, from that file:
   - `openhouse-db` — a managed Postgres instance
   - `openhouse-redis` — a managed Key Value (Redis/Valkey-compatible) instance
   - `openhouse-backend` — a web service built from `backend/Dockerfile`
4. During setup, Render prompts for the env vars marked `sync: false` in
   `render.yaml` — fill in:
   - `APP_URL` — your eventual frontend URL (a placeholder like
     `https://openhouse.example.com` is fine until the frontend exists)
   - `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` from
     step 1
5. Everything else (`DATABASE_URL`, `REDIS_URL`, `ADMIN_TOKEN`) is wired up
   or generated automatically — `DATABASE_URL` and `REDIS_URL` are injected
   from the Postgres/Key Value instances via `fromDatabase`/`fromService`,
   and `ADMIN_TOKEN` is a random value Render generates for you.
6. Click **Apply**. First deploy builds the Docker image and starts the
   service.

## 3. No manual migration step needed for this first deploy

The app calls `db.create_all()` on startup (see `app/main.py`'s `lifespan`),
which creates every table from `app/models.py` directly against whatever
Postgres database it's pointed at. That's enough to go from an empty
database to a fully working schema on first boot — you don't need to run
Alembic for this initial deploy.

Alembic (`backend/migrations/`) is there for *future* schema changes: once
the app is live with real data, use `alembic upgrade head` to apply new
migrations without dropping anything. On Render, run it either from the
**Shell** tab on the service (one-off), or — once you're on a paid compute
plan — by adding a `preDeployCommand: alembic upgrade head` to the
`openhouse-backend` service in `render.yaml` (Render's `preDeployCommand`
isn't available on the free compute plan).

## 4. Verify it's actually working

```bash
# Replace with your service's Render URL
BASE=https://openhouse-backend.onrender.com

# Create a room
curl -s -X POST "$BASE/api/rooms" \
  -H 'Content-Type: application/json' \
  -d '{"name": "Smoke Test Room", "owner_name": "Admin"}' | python3 -m json.tool

# Grab the admin token Render generated (Dashboard -> openhouse-backend -> Environment)
curl -s "$BASE/api/admin/metrics" -H "X-Admin-Token: <paste it>"
```

If you want to check the realtime path too, the live smoke-test pattern used
during development (connect two `websockets` clients, `auth`, `send_message`,
confirm both receive it) works the same way against the real URL — just
swap `ws://127.0.0.1:PORT/ws` for `wss://<your-service>.onrender.com/ws`.

## Notes / limits

- **Free-tier web services spin down on inactivity** and cold-start on the
  next request (a few seconds). That's fine for REST calls and for the
  client reconnect-with-backoff behavior the README describes, but it does
  mean a WebSocket connection left open during a long idle period could get
  dropped by the platform — the client is expected to reconnect, which the
  protocol already supports via `auth` + `last_seq`.
- **Key Value (Redis) free plan** has modest memory/connection limits —
  fine for an MVP pilot, not for production scale.
- `S3_REGION` defaults to `auto` in `render.yaml`, which is what Cloudflare
  R2 expects. Change it to a real AWS region if you used S3 instead.
