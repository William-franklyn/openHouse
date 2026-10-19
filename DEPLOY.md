# Deploying the Openhouse backend for free

Three services, all genuinely free with no expiry:

| Piece | Provider | Why |
|---|---|---|
| Web service (the app itself) | **Render** | Long-running process, not serverless - the WebSocket hub, its background Redis-listener task, and the async DB pool all need a process that stays alive, which Vercel's serverless Python functions don't provide. |
| Postgres | **Neon** | Render's free Postgres expires 30 days after creation (then gets deleted). Neon's free tier has no expiry and no credit card required - just a cold-start after 5 minutes idle, same flavor of trade-off as Render's free web service. |
| Redis (pub/sub, rate limits) | **Render Key Value** | Render's free Key Value plan (Valkey, Redis-protocol-compatible) doesn't expire, unlike its Postgres. No need to go elsewhere for this one. |
| File storage | **Cloudflare R2** | Render has no object storage at all. R2's free tier (10 GB, generous request quotas, zero egress fees) doesn't expire either. |

None of these require a credit card for the free tier. The only real constraint: Neon and Render's web service both sleep after a few minutes idle and take a moment to wake up on the next request - fine for a demo/pilot, not for guaranteeing instant response times.

## 1. Set up Neon (Postgres)

1. Sign up at [neon.tech](https://neon.tech), no credit card needed.
2. Create a project (any name/region).
3. Copy the connection string it gives you — it looks like:
   `postgresql://user:password@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require&channel_binding=require`
4. Paste it in as-is when Render asks for `DATABASE_URL` in step 3 below.
   `app/db.py`'s `normalize_database_url()` already handles picking the
   `asyncpg` driver and stripping `sslmode`/`channel_binding` (asyncpg
   doesn't accept those as connection kwargs the way other Postgres drivers
   do) into the SSL config asyncpg actually understands.

## 2. Set up object storage (Cloudflare R2)

1. [dash.cloudflare.com](https://dash.cloudflare.com) → **R2 Object Storage** → **Create bucket** (any name, e.g. `openhouse-files`).
2. **Manage API Tokens** → **Create API Token** → read/write access to that bucket.
3. Note down: **Endpoint URL** (`https://<account-id>.r2.cloudflarestorage.com`), **Bucket name**, **Access Key ID**, **Secret Access Key**.

(AWS S3 works too if you'd rather use that — same four values, leave the endpoint blank, use a real region like `us-east-1` instead of `auto`.)

## 3. Deploy the Render blueprint

Open **https://render.com/deploy?repo=https://github.com/William-franklyn/openHouse** (or in the dashboard: **New → Blueprint**, connect the `William-franklyn/openHouse` repo — Render reads `render.yaml` at the repo root automatically).

Render provisions, from `render.yaml`:
- `openhouse-redis` — a managed Key Value (Valkey/Redis-compatible) instance, free plan
- `openhouse-backend` — the web service, built from `backend/Dockerfile`, free plan

It'll prompt for every env var marked `sync: false`:
- `DATABASE_URL` — the Neon connection string from step 1
- `APP_URL` — a placeholder is fine (e.g. `https://openhouse.example.com`) — there's no frontend yet
- `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` — from step 2

`REDIS_URL` and `ADMIN_TOKEN` are wired up / generated automatically — you don't touch those.

Click **Apply**. First deploy builds the Docker image and starts the service.

## 4. No manual migration step needed for this first deploy

The app calls `db.create_all()` on startup (see `app/main.py`'s `lifespan`),
which creates every table from `app/models.py` directly against whatever
Postgres database it's pointed at — Neon in this case. That's enough to go
from an empty database to a fully working schema on first boot.

Alembic (`backend/migrations/`) is there for *future* schema changes: once
there's real data, run `alembic upgrade head` (pointed at the same Neon
`DATABASE_URL`) to apply new migrations without dropping anything. You can
run it from your own machine against Neon directly — no need for Render's
Shell tab or a paid `preDeployCommand` the way a Render-hosted Postgres
would need.

## 5. Verify it's actually working

```bash
# Replace with your service's Render URL
BASE=https://openhouse-backend.onrender.com

# Just confirm the process is up and routing (no DB/Redis/S3 involved)
curl -s "$BASE/healthz"

# Create a room (this one does touch Postgres - confirms Neon is reachable)
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

- **Render's free web service spins down after 15 min idle** and cold-starts
  on the next request (a few seconds). Fine for REST calls and for the
  client reconnect-with-backoff behavior the README describes; a WebSocket
  left open during a long idle period could get dropped by the platform —
  the client is expected to reconnect, which the protocol already supports
  via `auth` + `last_seq`.
- **Neon's free compute suspends after 5 min idle** too, with a similar
  cold-start on the next query. Both this and the point above mean: the
  very first request after a quiet period is slow, everything after it is
  normal speed.
- **Render Key Value (Redis) free plan** is 25 MB with no persistence —
  fine for an MVP pilot's rate-limit counters and pub/sub, not for
  production scale.
- **Neon free tier** is 1 GB storage / 100 CU-hours per month per project —
  plenty for an MVP pilot, not for production scale.
- `S3_REGION` defaults to `auto` in `render.yaml`, which is what Cloudflare
  R2 expects. Change it to a real AWS region if you used S3 instead.
