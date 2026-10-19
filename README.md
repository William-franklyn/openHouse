# Openhouse

**Chat with the people around you. No phone number, no account, just a code.**

Openhouse lets anyone create a **Room**: a group chat for one place or one moment (an open house anyone nearby can walk into), such as a hackathon, a conference, a class, a café or a camp. People join a Room with a short code (like `4F7K2`), a link or a QR code, using **their own internet** (mobile data or any Wi-Fi). They can use a name or stay anonymous, chat, share files, and leave when they want. The admin can pass admin rights to someone else before leaving, so the Room keeps living after its creator is gone.

**Wi-Fi is only used as a sign.** A host can rename their phone hotspot to something like `Openhouse 4F7K2`. People nearby see it in their Wi-Fi list, but **nobody needs to connect to it**. They just open Openhouse and type the code.

Founders: William Mahunda and Mike Maeda
Status: **MVP (v0.1)** — backend-first pass. See "Current implementation status" below.
First markets: **hackathons and conferences**, then **college campuses**, then **cafés/restaurants and camps** (adults only).

> **Naming note:** the app is **Openhouse** and chat groups are called **Rooms**. Put the app name, the room word and URLs in one config file (`APP_NAME`, `ROOM_WORD`, `APP_URL`), so renaming later is a one-line change.

This README is the full specification for the coding agent. If something is not covered here, pick the simplest option and list it under "Decisions" at the end.

---

## 0. Current implementation status

This pass built the **backend only** (FastAPI + SQLAlchemy + Redis pub/sub + S3-compatible storage), per an explicit scope decision — see the "scope" question/answer context. Not built yet: the Next.js frontend, QR code generation, the printable poster, and the Playwright end-to-end tests (section 10, items 12–15). Everything backend-related in sections 6–10 (items 1–11) is implemented and covered by an automated `pytest` suite.

**Deploying it:** see [`DEPLOY.md`](DEPLOY.md) for Render, which this app is set up for (`render.yaml` at the repo root). Vercel's serverless Python functions were tried first and don't work for this backend — see the Decisions entry on WebSocket-triggered logic and the Hub's background task, both of which need a long-lived process that serverless functions don't provide.

```
openhouse/
├── README.md
├── docker-compose.yml          # postgres + redis + minio + backend, for real local dev
└── backend/
    ├── Dockerfile
    ├── requirements.txt         # production deps
    ├── requirements-dev.txt     # + test deps (pytest, aiosqlite, fakeredis, moto)
    ├── alembic.ini
    ├── pytest.ini
    ├── app/
    │   ├── main.py              # FastAPI app, REST routes, the /ws endpoint, admin API
    │   ├── config.py            # APP_NAME, ROOM_WORD, APP_URL, every limit
    │   ├── models.py            # SQLAlchemy models for section 6's data model
    │   ├── db.py                # async engine/session factory
    │   ├── security.py          # token/device hashing, recovery-code hashing, code generators
    │   ├── errors.py            # DomainError -> the error codes in section 8
    │   ├── rooms.py              # room lifecycle: codes, settings, deletion, owner recovery
    │   ├── members.py           # join flow, sessions, roles, kicks, bans
    │   ├── messages.py          # channels, seq'd messages, history, pins, delete
    │   ├── safety.py             # rate limits, reports
    │   ├── files.py              # S3-compatible storage, upload/download
    │   ├── realtime.py           # WebSocket hub, Redis pub/sub fan-out, per-message dispatch
    │   └── metrics.py            # daily counters
    ├── migrations/               # Alembic, targets Postgres in production
    └── tests/                    # pytest, runs against SQLite + fakeredis + moto (see Decisions)
```

This file (and the numbered sections below) is kept as the **full product spec**, not just a backend spec — the frontend sections (3, 5, 9) describe what still needs to be built next.

---

## 1. Key terms

| Term | Meaning |
|---|---|
| **Room** | A group chat room. Has a name, a code, settings, members and channels. |
| **Room code** | 5 characters from `23456789ABCDEFGHJKMNPQRSTUVWXYZ` (no 0/O/1/I/L), e.g. `4F7K2`. Shown big, as a link and as a QR code. |
| **Join link** | `APP_URL/r/<code>` (the QR code points here). |
| **Owner (admin)** | The one person with full control. Exactly one per Room. Can hand ownership to another member. |
| **Moderator** | A helper chosen by the owner. Can remove messages and members and pin announcements, but cannot delete the Room or change the owner. |
| **Member** | Anyone who joined. Can chat, share files and report. |
| **Device session** | No accounts in v0.1. Each browser gets a private session token when it joins. |
| **Beacon** | Advertising a Room code in the area, via the Wi-Fi hotspot name or a printed QR poster. Nobody connects to it. |

---

## 2. MVP goals (must build)

### Rooms
1. **Create a Room** with a name (3–40 characters) and an optional end time. No account needed. The creator becomes the owner.
2. **Owner recovery code.** On creation, show a one-time **owner recovery code** (12 characters) with "Save this to get admin back if you lose this device." Entering it on another device restores ownership.
3. **Join policy,** chosen by the owner and changeable any time:
   - `open`: anyone with the Room code can join (the default; best for events).
   - `approval`: people with the code ask to join, and the owner or a moderator approves.
   - `invite_only`: the Room code alone is not enough. A one-time **invite code** is needed (single use, expires after 15 min).
4. **Who can invite** (only for `invite_only`): `admins` (owner + moderators) or `members`.
5. **New code.** The owner can generate a new Room code. The old code stops working immediately; existing members stay.
6. **Room ends** at its end time, or when the owner deletes it. **Only the owner can delete a Room.** Deleting removes all messages and files for everyone. A Room with no end time stays open until deleted.
7. **Hand over ownership.** The owner picks a member, who must **accept**. The new owner gets full control; the old owner becomes a normal member. Everyone sees `Mike is now the owner of this Room.` If the owner is the last member and leaves, the Room stays open, and the owner can restore ownership with the recovery code.

### People
8. **Name or anonymous** on join: a display name (1–24 characters), or "Stay anonymous", which shows as `Guest-1234`. A member can change their name later.
9. **Age gate:** joining requires ticking "I am 18 or older" (v0.1 is adults-only). Room rules are shown before joining.
10. **Leave and rejoin.** The browser remembers the session, so "Rejoin" works without the code. "Leave Room" removes the member completely; joining again needs the current code or a new invite.

### Chat
11. **Channels.** Every Room has `#general`. Owner and moderators can create up to 10 more, e.g. `#find-a-team`, `#help`, `#food`.
12. **Real-time messages** (1–2000 characters), in the same order for everyone. History loads when you open a channel, 50 messages at a time when scrolling up.
13. **Announcements.** Owner and moderators can pin up to 3 messages at the top of the Room.
14. **Files and images** up to **10 MB**: images, PDFs, docs and zip files. Images show a preview.
15. **Online list** with role badges (Owner, Mod).

### Safety (required from day one)
16. **Report** a message or member. Reports go to the owner, moderators, and a platform admin queue.
17. **Block** a member: you no longer see their messages (on your device only).
18. **Remove** (kick) a member, or **ban** them. Ban blocks their session and device fingerprint from rejoining this Room.
19. **Delete message:** your own, or anyone's if you are owner or moderator.
20. **Rate limits:**
    - messages: 10 per 10 s per member
    - join attempts: 10 per minute per IP, which stops people guessing codes
    - file uploads: 5 per minute per member
21. **Platform admin page** (for the founders): see reports, remove Rooms or messages, and ban abusers across the platform.

### Beacon (advertising a Room nearby)
22. The Room's share screen shows:
    - the code in big letters, the join link, and a QR code
    - a **printable poster** (PDF/print view) with the Room name, code and QR, for tables, badges and screens
    - **"Advertise with your hotspot"**: suggests the hotspot name `Openhouse 4F7K2` (max 32 characters) and short steps for iPhone (the hotspot name is the phone's name, under Settings → General → About → Name) and Android (Settings → Hotspot → Hotspot name). It also says: *"People don't need to connect, they just read the code. Your hotspot uses battery; turn it off when you're done."*

### Metrics (for us, counts only; never message content)
23. Track per day:
    - Rooms created
    - joins (named vs. anonymous)
    - messages sent
    - files shared
    - ownership handovers
    - how long Rooms stay active
    - members who come back on another day

    Show these on the platform admin page.

### Out of scope for v0.1 (do NOT build; see Roadmap)
- Native iOS/Android apps (v0.1 is a mobile-first web app that can be added to the home screen, a PWA).
- Accounts, phone numbers, email login, contacts.
- Push notifications.
- End-to-end encryption (v0.1 uses HTTPS, with data encrypted on the server).
- Finding Rooms near you automatically (Bluetooth or location).
- Payments and organizer plans.
- Voice and video.

---

## 3. Architecture

```
  Phones / laptops (browser, PWA)
        │   HTTPS + secure WebSocket (WSS) over their own internet
        ▼
  ┌──────────────────────────┐        ┌───────────────┐
  │  API + realtime server    │◄──────►│  Redis        │  pub/sub between server
  │  (FastAPI, Python)        │        │               │  instances, rate limits,
  │  REST + WebSocket         │        └───────────────┘  online presence
  └───────────┬──────────────┘
              │
     ┌────────┴─────────┐
     ▼                  ▼
  PostgreSQL       Object storage (S3-compatible)
  Rooms, members,  uploaded files; downloads via
  messages, etc.   short-lived signed URLs
```

- **Client/server.** Every device only makes **outgoing** HTTPS/WSS connections, so it works on school, café, hotel and mobile networks without any special setup.
- **Several server instances** can run at once. Every event is published to Redis, and each instance forwards it to its own connected clients.
- **Ordering:** each message gets an increasing `seq` per channel from PostgreSQL (in a transaction), and clients sort by `seq`.

**Implemented this pass:** the realtime Hub (`app/realtime.py`) registers each WebSocket locally per process and publishes every event to one Redis pub/sub channel; every Hub instance (including the one that published) is subscribed to that channel, so a single publish naturally fans out to every connected client on every server process — this is what makes multi-instance delivery work (verified with two `Hub` instances sharing one Redis in `tests/test_realtime.py`).

---

## 4. Tech stack

| Part | Choice |
|---|---|
| Backend | Python 3.12, **FastAPI**, Uvicorn, SQLAlchemy 2 + Alembic migrations |
| Realtime | FastAPI WebSockets + **Redis** pub/sub |
| Database | **PostgreSQL** |
| Files | S3-compatible storage (AWS S3, Cloudflare R2, or similar) |
| Frontend | **Next.js** (React, TypeScript), mobile-first, installable PWA — *not built this pass* |
| QR codes | `qrcode` library (frontend) — *not built this pass* |
| Tests | `pytest` + `httpx` (backend, done); Playwright (end-to-end, *not built this pass*) |
| Local dev | `docker compose` with Postgres, Redis and MinIO (local S3) |
| Hosting | Backend on an always-on host that supports long-lived WebSockets (Render, Railway or Fly.io). Frontend can go on Vercel. |

Clients must **auto-reconnect** with backoff (1 s, 2 s, 4 s… max 15 s) and resume from the last `seq` they saw, because hosting platforms can drop long connections. (The server side of this — `auth` with `last_seq`, replaying missed messages — is implemented; the client-side reconnect backoff is a frontend concern, not built this pass.)

---

## 5. Project layout

See section 0 for the layout actually built this pass. The `frontend/` tree below is the target for the next pass:

```
frontend/
├── app/                   # Next.js pages
│   ├── page.tsx           # home: Join with code / Create a Room
│   ├── r/[code]/page.tsx  # join screen
│   ├── room/[id]/page.tsx # chat screen
│   └── admin/page.tsx     # platform admin
├── components/
└── lib/                   # API + WebSocket client
```

Keep logic (`rooms.py`, `members.py` …) separate from HTTP/WebSocket code so it can be tested on its own. (Done: every module above is plain async functions over a DB session — `main.py` and `realtime.py` are the only places that know about HTTP/WebSocket.)

---

## 6. Data model (PostgreSQL)

```
rooms      (id, name, code UNIQUE, join_policy, invite_by, owner_member_id,
            owner_recovery_hash, ends_at NULL, created_at, deleted_at NULL)
members    (id, room_id, display_name, is_anonymous, role [owner|mod|member],
            session_token_hash, device_hash, invited_by_member_id NULL,
            status [pending|active|left|removed|banned], last_seen_at, created_at)
channels   (id, room_id, name, position, created_at)
messages   (id, channel_id, seq, member_id, kind [text|file|system], text NULL,
            file_id NULL, deleted_at NULL, created_at)   UNIQUE(channel_id, seq)
pins       (room_id, message_id, position)
files      (id, room_id, member_id, storage_key, filename, size, mime, created_at)
invites    (code, room_id, created_by_member_id, expires_at, used_by_member_id NULL)
reports    (id, room_id, reporter_member_id, target_member_id NULL, message_id NULL,
            reason, status [open|done], created_at)
metrics_daily (day, name, value)
```

- Store **hashes** of session tokens and the recovery code, never the raw values (SHA-256 for tokens; argon2 or bcrypt for the recovery code).
- When a Room is deleted or ends, delete its messages, files (including storage objects) and invites **within 24 hours**. Keep reports for 30 days for safety, then delete them.

(`channels` also has a `next_seq` counter column not in the sketch above — see Decisions, "gap-free seq".)

---

## 7. Sessions, codes and roles

- **Join flow:** `POST /api/rooms/{code}/join` with `{name | anonymous, over_18: true, invite_code?}`. It returns `{member_id, room_id, session_token, status}`.
- `session_token` = `secrets.token_urlsafe(32)`. It is stored in the browser (`localStorage`, wrapped in try/catch), keyed by `room_id`, and sent as `Authorization: Bearer` on REST calls and as the first WebSocket message.
- `device_hash`: a random ID created once per browser and stored in `localStorage`, hashed on the server. It's used only to enforce bans. This is not tracking; don't use any fingerprinting libraries.
- **Room codes** must be unique among active Rooms. Retry generation on collision.
- **Permission table** (enforce on the server, always):

| Action | Owner | Mod | Member |
|---|---|---|---|
| Chat, share files, report, block | ✓ | ✓ | ✓ |
| Create invite (invite_only) | ✓ | ✓ | if `invite_by = members` |
| Approve join requests | ✓ | ✓ | – |
| Pin, delete others' messages, remove/ban | ✓ | ✓ (not the owner or other mods) | – |
| Create/rename channels | ✓ | ✓ | – |
| Change join policy, new code, end time | ✓ | – | – |
| Add/remove moderators | ✓ | – | – |
| Hand over ownership | ✓ | – | – |
| **Delete Room** | ✓ | – | – |

---

## 8. API

### REST (JSON, under `/api`)

| Method & path | Who | What |
|---|---|---|
| `POST /rooms` | anyone | Create. Body `{name, ends_at?, owner_name?}`. Returns room + owner session + **recovery code** (shown once). |
| `GET /rooms/by-code/{code}` | anyone | Public preview: name, member count, join policy, rules. Never returns members or messages. |
| `POST /rooms/{code}/join` | anyone | Join (see section 7). `approval` → status `pending`. |
| `POST /rooms/{id}/recover-owner` | anyone | Body `{recovery_code}`. Gives this device a new owner session. |
| `GET /rooms/{id}` | member | Room details, channels, my role |
| `PATCH /rooms/{id}` | owner | Name, join_policy, invite_by, ends_at |
| `POST /rooms/{id}/new-code` | owner | Rotate the Room code |
| `DELETE /rooms/{id}` | **owner only** | Delete the Room |
| `POST /rooms/{id}/invites` | per table | Create a single-use invite |
| `GET /rooms/{id}/channels/{cid}/messages?before_seq=` | member | History, 50 at a time |
| `POST /rooms/{id}/files` | member | Upload a file directly (see Decisions — simplified from a presigned-URL flow) |
| `GET /files/{fid}` | member | Short-lived (5 min) signed download URL |
| `POST /rooms/{id}/reports` | member | Report a message or member |
| `GET /admin/...` | platform admin | Reports, metrics, takedowns (protected by an `ADMIN_TOKEN` env var for v0.1) |

### WebSocket `/ws`
First message: `{"type": "auth", "session_token": "...", "last_seq": {channel_id: seq}}`. The server replies `ready`, then sends any missed events.

**Client → server:**
- `send_message {channel_id, text, client_id}`
- `typing {channel_id}` (optional — not implemented, see Decisions)
- `delete_message {message_id}`
- `pin {message_id}`, `unpin {message_id}`
- `approve_member {member_id}`, `reject_member {member_id}`
- `remove_member {member_id}`, `ban_member {member_id}`
- `set_role {member_id, role: mod | member}`
- `offer_ownership {member_id}`, `answer_ownership {accept}`
- `create_channel {name}`
- `rename {display_name}`
- `leave`

**Server → client:**
- `ready`
- `message {channel_id, seq, ...}`
- `message_deleted`
- `pins`
- `member_joined`, `member_left`
- `presence {online: [...]}`
- `join_request` (see Decisions — currently broadcast room-wide, not admin-only)
- `role_changed`
- `ownership_offer {from_name}`, `ownership_changed {new_owner_id}`
- `channel_created`
- `removed {reason}`
- `room_deleted`
- `room_ended`
- `error {code, message}`

Use `client_id` to remove duplicate sends after a reconnect.

**Error codes:** `bad_code`, `bad_invite`, `pending_approval`, `banned`, `not_allowed`, `rate_limited`, `file_too_large`, `file_type`, `room_ended`, `bad_request`.

All user text must be shown with safe rendering (React's default escaping; never `dangerouslySetInnerHTML`). *(Frontend concern — not built this pass; the backend never does any HTML rendering of user text.)*

---

## 9. Screens (mobile first, clean, black and white with one accent color)

*Not built this pass — these are the target screens for the Next.js frontend.*

1. **Home:** a big "Enter Room code" box with a **Join** button, a "Scan QR" button (camera), and **Create a Room**.
2. **Join screen** (`/r/<code>`):
   - Room name, member count and rules
   - name field, or **Stay anonymous**
   - "I am 18 or older" checkbox
   - **Join** button
   - invite code field if `invite_only`
   - a "Waiting for approval…" state if `approval`
3. **Create Room:**
   - name and optional end time
   - then the **share screen**: big code, link, QR, **Print poster**, **Advertise with your hotspot**
   - the **owner recovery code**, with a "Copy" button and an "I saved it" button before continuing
4. **Chat:**
   - top: channel tabs and pinned announcements
   - middle: message list
   - bottom: input with file button
   - a side or bottom sheet for the members list
5. **Room settings** (owner): join policy, who can invite, new code, end time, moderators, **Hand over ownership**, **Delete Room** (with a confirm that requires typing the Room name).
6. **Member menu** (tap a name): Block, Report. Admins also see Remove, Ban, Make moderator, Offer ownership (owner only).
7. **Platform admin** (`/admin`): reports queue, metrics, takedown buttons.

---

## 10. Tests

**Backend (pytest) — implemented in `backend/tests/`:**
1. Room codes use only the allowed characters, are unique, and a new code stops the old one working. → `test_rooms.py::test_room_code_alphabet_and_uniqueness`, `::test_new_code_stops_old_code_working`
2. All three join policies. Invites are single use and expire after 15 minutes (mock the time). → `test_rooms.py::test_open_join_policy`, `::test_approval_join_policy`, `::test_invite_only_join_policy_single_use_and_expiry`, `::test_who_can_invite_setting`
3. Every row of the permission table, including *only the owner can delete*. → `test_rooms.py::test_only_owner_can_delete_room`, `test_members.py::test_owner_can_remove_mod_and_member`, `::test_mod_cannot_remove_owner_or_other_mod`, `::test_set_role_owner_only`
4. Ownership handover: needs acceptance; after it, roles are swapped; a declined offer changes nothing. → `test_members.py::test_ownership_handover_requires_acceptance_and_swaps_roles`, `::test_ownership_handover_declined_changes_nothing`
5. The recovery code restores ownership; a wrong code fails, with rate limiting. → `test_rooms.py::test_recovery_code_restores_ownership`, `::test_recovery_rate_limited`
6. Bans block rejoin with the same session or device ID. → `test_members.py::test_ban_blocks_rejoin_by_session_and_device`, `::test_kicked_member_can_rejoin_with_new_join_unlike_banned`
7. Rate limits trigger and send `rate_limited`. → `test_realtime.py::test_message_rate_limit_triggers`, `::test_upload_rate_limit_triggers`, `::test_join_rate_limit_triggers`
8. Message `seq` increases per channel with no gaps under concurrent sends; a reconnect with `last_seq` gets exactly the missed messages. → `test_realtime.py::test_seq_increases_with_no_gaps_under_concurrent_sends`, `::test_reconnect_with_last_seq_gets_exactly_missed_messages`
9. Files: size and type limits, signed URLs only for members, and files deleted when the Room is deleted. → `test_files.py` (all five tests)
10. Deleted or ended Rooms: join gives `room_ended`, and data is cleaned up. → `test_rooms.py::test_deleted_room_join_gives_room_ended_and_cleans_up`, `::test_ended_room_by_timer_gives_room_ended_on_join`
11. Two server instances with Redis: a message sent to instance A reaches a client on instance B. → `test_realtime.py::test_message_reaches_client_on_a_different_instance_via_redis`

Plus `test_safety.py` for reports reaching the admin queue and daily metrics counting — not separately numbered above, but part of section 2's safety/metrics goals.

Run with:
```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

**End-to-end (Playwright, two or three browser contexts) — not built this pass, needs the frontend first:**

12. Create a Room → a second browser joins via the link → both chat → file shared and downloaded.
13. Anonymous join shows `Guest-####`.
14. Ownership handover, then the old owner can no longer delete the Room.
15. Report a message → it appears in the platform admin queue.

---

## 11. Pilot script (what we show at the first hackathon)

1. The organizer creates a Room "HackAlfred 2026", saves the recovery code, and prints the poster for each table.
2. The organizer's phone hotspot is renamed `Openhouse 4F7K2`. Attendees see it in their Wi-Fi list and type the code. Others scan the QR.
3. Attendees join, some anonymous, and post in `#find-a-team`.
4. The organizer pins "Pizza at 7 pm in Hall B" and makes two volunteers moderators.
5. Someone posts spam → it's reported → a moderator removes the message and the member.
6. The organizer leaves early and hands ownership to a volunteer, who accepts. The Room keeps running.
7. After the event, the new owner deletes the Room.
8. We check the metrics: joins, messages, how many came back.

(Not runnable end to end yet — needs the frontend, the poster, and the hotspot-name helper text, none of which exist yet. Every backend step above (create, join, pin, moderate, handover, delete, metrics) works today via the API.)

---

## 12. Roadmap (context only, do NOT build in v0.1)

- **v0.2:** push notifications; email login (optional) to keep your Rooms across devices; organizer dashboard (attendance, announcements, export).
- **v0.3: Native apps.** **Bluetooth "Rooms near you"** (phones advertise the Room code over Bluetooth LE, so nearby people see it without anyone touching hotspot settings), and offline local mode for places with no signal.
- **v0.4:** end-to-end encryption for private Rooms; paid organizer plans (custom branding, bigger files, analytics).
- **Later:** long-living Rooms tied to a place (a campus building, a coworking space, a city square), passed from owner to owner.

---

## 13. Definition of done (v0.1)

- All tests pass, and `docker compose up` runs the full app locally. *(Backend tests pass; `docker compose up` brings up Postgres/Redis/MinIO/backend correctly by inspection, but wasn't actually run against real Docker in this environment — see Decisions. No frontend container yet.)*
- Deployed to staging with HTTPS, and it works on iPhone Safari and Android Chrome over mobile data **and** on a campus Wi-Fi. *(Not done — no frontend, no deployment this pass.)*
- The pilot script (section 11) works end to end. *(Backend half works; see section 11 note.)*
- No crashes on bad input; errors are shown to users in plain words. *(Backend: yes, every handler raises a typed `DomainError` with a plain-English message, caught centrally.)*

## Decisions
_(Coding agent: list choices you made that this README did not specify.)_

**Scope for this pass.** The user explicitly chose "backend-first MVP" over "the full stack" or "just save the spec" when asked — see section 0. Everything below is about the backend only.

**Test infrastructure substitutes, not architecture substitutes.** The spec names PostgreSQL, Redis, and S3-compatible storage. This sandbox has no Docker, no local Postgres, and no local Redis/MinIO server, and installing Docker Desktop wasn't appropriate to do unprompted. So:
- **Database:** `app/models.py` avoids every Postgres-only feature (no ARRAY/JSONB, no native enums, no `DateTime(timezone=True)` — see "naive UTC" below), so the identical models work against `sqlite+aiosqlite` in tests and real PostgreSQL (via `asyncpg`) in production, selected purely by `DATABASE_URL`. Alembic's scaffold (`migrations/`) was validated by actually generating the initial revision against a throwaway SQLite file and reading the output — it correctly captured every table/index/constraint.
- **Redis:** tests use `fakeredis.FakeAsyncRedis`, which mirrors the real `redis.asyncio` API closely enough that `app/realtime.py` and `app/safety.py` never know the difference. The multi-instance fan-out test (#11) builds two separate `Hub` instances, each with its own `FakeAsyncRedis` client pointed at the *same* `fakeredis.FakeServer` — i.e. two independent "server processes" sharing one Redis, which is exactly the scenario the real deployment needs to handle.
- **S3:** tests use `moto`'s `mock_aws()`. One real gotcha hit and fixed: moto only intercepts boto3 calls to the *default* AWS endpoint — passing a custom `endpoint_url` (which production needs, to point at MinIO/R2) makes `moto` let the real HTTP call through, which then hangs for ~10s trying to reach a MinIO that isn't running, and looks exactly like a frozen test. Fixed by making `Storage` omit `endpoint_url` entirely when unset (`app/files.py`), and having the test `Settings` fixture set `S3_ENDPOINT_URL=None` while production keeps a real MinIO/R2 URL.
- **Validated for real, not just by inspection:** besides the pytest suite (33 tests, all passing), a standalone script spun up the actual FastAPI app under real `uvicorn` (with its real `lifespan`, so `db.create_all()` and `hub.start()` ran for real) and drove it with the real `websockets` client library over actual loopback sockets — create room → join → both connect to `/ws` → chat message delivered with the right `seq`. This specifically exercises the one piece the pytest suite deliberately bypasses (see next point).

**WebSocket-triggered logic is tested by calling `realtime.dispatch()` directly, not through a live WebSocket.** `tests/conftest.py`'s `FakeWebSocket` + `register_socket()` + `ws_dispatch()` register a fake socket on the real `Hub` and call the real `realtime.dispatch()` — the actual production code for every WS message type — without going through `starlette`'s WebSocket test machinery, which doesn't mix cleanly with async fixtures that already own a specific event loop (a `TestClient.websocket_connect()` runs in its own thread/loop, and the `aiosqlite`/`fakeredis` objects built in this test's loop would cross loop boundaries). This is faster and more deterministic than real sockets, and it exercises 100% of the business logic; the thin `@app.websocket("/ws")` adapter in `main.py` (auth, resume, the receive loop) is covered by the standalone live smoke test above instead of by an automated pytest test.

**Naive UTC everywhere, not timezone-aware.** SQLite (test-only) silently drops tzinfo when a `DateTime(timezone=True)` value round-trips through it, while Postgres (production) preserves it — so a tz-aware `utcnow()` compared against a value just read back from SQLite raises `TypeError: can't compare offset-naive and offset-aware datetimes`. Hit this for real in the invite-expiry and room-ends-at tests. Fixed by making `utcnow()` return naive UTC consistently and normalizing any externally-supplied datetime (e.g. a browser-sent `ends_at`) through `to_naive_utc()` before storing it. Every stored timestamp is implicitly UTC; none carry an explicit offset.

**`metrics.bump()` is upsert-with-retry, not select-then-branch.** The first version did `SELECT`, then `INSERT` if missing else `UPDATE` — two concurrent bumps of the same `(day, name)` counter (e.g. two chat messages sent in parallel) can both see "no row yet" and both `INSERT`, and the second hits the unique constraint and crashes. Caught this via the concurrent-seq test (#8), which sends 10 messages with `asyncio.gather`. Fixed to try an atomic `UPDATE ... SET value = value + :by` first (a single statement, safe under concurrency on both SQLite and Postgres), and only `INSERT` if that affected zero rows, with an `IntegrityError` fallback to the same `UPDATE` in case another transaction won the race in between.

**File uploads go through our own server, not a client-direct-to-S3 presigned-POST flow.** The README's sketch is `POST /rooms/{id}/files` → signed upload URL → client uploads directly to S3 → `POST /files/{fid}/complete`. Simplified to a single multipart `POST` through our server (same approach as our other project, Hotspot Hangout), because (a) it's one request instead of three, (b) there's no frontend yet to drive a real presigned PUT/POST, and (c) testing a genuine client-to-S3 presigned upload against `moto` needs either `moto`'s HTTP-level server mode or stubbing `requests`, neither of which was worth the complexity for this pass. Downloads still use a real short-lived presigned GET URL (5 minutes), which is the part that actually benefits from bypassing our server, and is trivial to generate/verify with `moto`.

**`join_request` is broadcast room-wide, not admin-only.** Properly restricting `join_request` to owner/mod sockets *across every server instance* needs each `Hub` to track roles for its own locally-connected sockets and keep that in sync as roles change — doable, but not load-bearing for the test list, so it's deferred. Every actual *permission* (approving, rejecting, moderating) is still enforced server-side regardless of who sees the notification; this is a UX/privacy simplification, not a security gap. `ownership_offer`, `removed` (kick/ban), and `kicked`-style socket closes *are* properly single-target (`to_member_id` in the Redis payload), since that only needs one ID, not a role lookup.

**Room/file/invite deletion is immediate, not 24-hours-delayed.** The README asks for messages/files/invites to be deleted "within 24 hours" of a Room ending or being deleted. A real delayed cleanup needs a background scheduler (Celery/APScheduler/a cron-triggered endpoint), which felt like a disproportionate addition for an MVP pass. `rooms.delete_room()` deletes everything synchronously, immediately. The Room row itself is soft-deleted (`deleted_at` set, row kept) rather than hard-deleted, so it still exists for metrics/history purposes.

**Closing a member's own WebSocket never blocks the realtime path.** `leave`, `remove_member`, and `ban_member` all finish every state change (and, for the Hub's dispatch, the `send_json` of the "you were removed" event) *before* calling `ws.close()`, and do the actual close via a fire-and-forget background task (`asyncio.ensure_future`) rather than awaiting it inline. A WebSocket closing itself from inside its own message-handling coroutine has to wait out a real close-handshake timeout (~10s) if the peer doesn't immediately acknowledge it — if that wait happened synchronously, one member leaving could stall every other realtime event in that room (or, since the Hub's listener loop is shared across rooms per process, in *every* room on that server instance) for ten seconds. This is the same bug class — and the same fix — as one found and fixed in Hotspot Hangout; recognizing the pattern here avoided re-discovering it the slow way.

**Only one admin-login identity per Room; owner recovery reuses it.** `room.owner_member_id` always points at the one `Member` row that currently holds the owner role. `recover-owner` doesn't create a new member — it resets that existing row's `session_token_hash`/`device_hash` to the new device's and reactivates it (`status = "active"`), consistent with "if the owner is the last member and leaves, the Room stays open, and the owner can restore ownership with the recovery code" (i.e. recovery has to work even if that row's `status` was `"left"`).

**Renaming (`rename` over WS) doesn't get its own named broadcast event** — the WS event table in section 8 has no "member renamed" event. Reusing `presence` (which already carries `{member_id, name, role}` for everyone online) to also cover name changes avoided inventing an event type the spec didn't ask for, at the cost of presence being reused as "the roster," not strictly "who's online." Noted in case the frontend expects a narrower `presence` meaning.

**Invite/room/download lookups that fail are told apart as little as possible.** E.g. "banned" vs. "wrong recovery code" vs. "unknown room" each map to the error codes the README actually lists (`banned`, `not_allowed`, `bad_code`) rather than inventing new ones, even where a more specific code would have been nice (there's no `bad_recovery_code` in the spec's list, so a wrong recovery code is reported as `not_allowed`).

**Admin auth is a single shared `ADMIN_TOKEN` header (`X-Admin-Token`), not a login flow**, matching "protected by an `ADMIN_TOKEN` env var for v0.1" in section 8's table — there's no platform-admin user model at all yet, intentionally (that's accounts, which is explicitly out of scope for v0.1).

**A module-level `app` was added to `main.py` for ASGI auto-discovery** (Vercel's build step, plain `uvicorn app.main:app`, etc.), alongside the existing `create_app()` factory the test suite uses. This was only safe to add after also fixing `Storage.__init__` to stop making a real network call (`head_bucket`/`create_bucket`) at construction time — previously harmless because `create_app()` was only ever called from controlled contexts (tests, or just before `uvicorn.run`), but a bare `app = create_app()` at import time would otherwise run that network call on *every* import of `app.main`, including every test file, hanging for ~10s each on an unreachable S3 endpoint (see the moto `endpoint_url` entry above — same failure mode, new trigger). The bucket-exists check now runs once from the async `lifespan` startup via `Storage.ensure_bucket()`, awaited through `asyncio.to_thread` so it doesn't block the event loop.

**Deploying to Vercel doesn't work for this backend and wasn't pursued further than diagnosing why**, once that became clear — see the top-of-file deployment note and `DEPLOY.md`. Render was picked instead (user's choice between Render/Railway/Fly.io, all three of which the README already names as suitable). Two real compatibility issues surfaced while wiring up `render.yaml` and were fixed in code rather than worked around in config: (1) Render's Postgres `connectionString` is a bare `postgres://`/`postgresql://` URL with no driver named, which SQLAlchemy's async engine needs (`+asyncpg`) — fixed with `normalize_database_url()` in `app/db.py`, which also leaves already-correct and SQLite URLs untouched; (2) Render expects the container to bind to its `$PORT` env var (default 10000) rather than a fixed port — fixed by switching the Dockerfile's `CMD` to shell form so `${PORT:-8000}` actually expands (exec-form array syntax doesn't do shell substitution). Render's managed "Key Value" product is Valkey under the hood, Redis-protocol-compatible, so `redis.asyncio` and `fakeredis` both work against it unchanged; the blueprint's `type: keyvalue` (not the deprecated `redis` alias) reflects Render's current naming.
