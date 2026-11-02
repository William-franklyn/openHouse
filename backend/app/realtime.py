"""WebSocket hub: local connection registry + Redis pub/sub fan-out.

Every event (to one room, or to one specific member) is published to a
single Redis channel as {"room_id", "event", "to_member_id", "close_after"}.
Every Hub instance (one per server process) subscribes to that channel and
only delivers to the sockets it personally holds — including its own
publishes, since a subscriber always receives its own published messages
too. That gives us both local delivery and multi-instance fan-out through
one code path, which is what SPEC.md test #11 (two instances, one message)
depends on.
"""

import asyncio
import json
import time

from sqlalchemy import select

from app import files as files_mod
from app import games as games_mod
from app import members as members_mod
from app import messages as messages_mod
from app import music_library
from app import card_games as card_games_mod
from app import party_games as party_games_mod
from app import rooms as rooms_mod
from app.errors import DomainError
from app.models import Channel, Member, Message, PartyGame, Room, new_id


async def _close_quietly(ws):
    try:
        await ws.close()
    except Exception:
        pass


class Hub:
    CHANNEL = "openhouse:events"

    def __init__(self, redis, db=None):
        self.redis = redis
        # Lets a fired party-round timer open its own fresh DB session -
        # it routinely outlives the WS connection/request session that
        # started it. None in any context that never arms a party timer
        # (e.g. older test fixtures) - schedule_party_timer's callers
        # always go through code paths that pass a real db.
        self.db = db
        self.local: dict[str, dict[str, object]] = {}
        self.pending_offers: dict[str, str] = {}
        # One in-process asyncio.sleep task per live party-game round (or
        # per post-reveal pause), keyed by party_game_id - never more than
        # one entry per key, since a game is always waiting on exactly one
        # of those two things at a time. Viable because this app deploys
        # as exactly one long-running process (render.yaml/DEPLOY.md): only
        # the instance that started/advanced the round runs this task; when
        # it fires, the callback goes through hub.publish, which already
        # fans out to every instance via Redis pubsub regardless of which
        # instance's timer fired. If this instance crashes mid-round, the
        # timer is lost with no server-side fallback - accepted MVP
        # tradeoff, same spirit as SPEC.md's room-deletion scheduler note.
        self.party_timers: dict[str, asyncio.Task] = {}
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        for key in list(self.party_timers.keys()):
            self.cancel_party_timer(key)
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    def schedule_party_timer(self, key: str, delay_seconds: float, callback) -> None:
        """Arms an in-process delayed callback, replacing any existing
        timer under `key` - the one generic primitive behind both a
        round's question-deadline and its post-reveal pause (two uses of
        the same mechanism)."""
        self.cancel_party_timer(key)

        async def _run():
            try:
                await asyncio.sleep(delay_seconds)
            except asyncio.CancelledError:
                return
            self.party_timers.pop(key, None)
            await callback()

        self.party_timers[key] = asyncio.create_task(_run())

    def cancel_party_timer(self, key: str) -> None:
        task = self.party_timers.pop(key, None)
        if task is not None:
            task.cancel()

    async def _listen(self) -> None:
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(self.CHANNEL)
        try:
            async for raw in pubsub.listen():
                if raw.get("type") != "message":
                    continue
                try:
                    payload = json.loads(raw["data"])
                except (TypeError, ValueError):
                    continue
                await self._deliver(payload)
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(self.CHANNEL)
            await pubsub.aclose()

    async def _deliver(self, payload: dict) -> None:
        room_id = payload.get("room_id")
        event = payload.get("event")
        to_member_id = payload.get("to_member_id")
        close_after = payload.get("close_after", False)

        conns = self.local.get(room_id)
        if not conns:
            return

        for member_id, ws in list(conns.items()):
            if to_member_id is not None and member_id != to_member_id:
                continue
            try:
                await ws.send_json(event)
            except Exception:
                continue
            if close_after:
                self.unregister(room_id, member_id)
                asyncio.ensure_future(_close_quietly(ws))

    async def publish(
        self, room_id: str, event: dict, to_member_id: str | None = None, close_after: bool = False
    ) -> None:
        payload = {
            "room_id": room_id,
            "event": event,
            "to_member_id": to_member_id,
            "close_after": close_after,
        }
        await self.redis.publish(self.CHANNEL, json.dumps(payload))

    def register(self, room_id: str, member_id: str, ws) -> None:
        self.local.setdefault(room_id, {})[member_id] = ws

    def unregister(self, room_id: str, member_id: str) -> None:
        conns = self.local.get(room_id)
        if conns and member_id in conns:
            del conns[member_id]
            if not conns:
                del self.local[room_id]

    async def presence_add(self, room_id: str, member_id: str) -> None:
        await self.redis.sadd(f"presence:{room_id}", member_id)

    async def presence_remove(self, room_id: str, member_id: str) -> None:
        await self.redis.srem(f"presence:{room_id}", member_id)


def _decode(value) -> str:
    return value.decode() if isinstance(value, bytes) else value


async def presence_snapshot(session, redis, room_id: str) -> list[dict]:
    raw_ids = await redis.smembers(f"presence:{room_id}")
    member_ids = [_decode(v) for v in raw_ids]
    online = []
    for member_id in member_ids:
        member = await session.get(Member, member_id)
        if member is not None and member.status == "active":
            online.append(
                {"member_id": member.id, "name": member.display_name, "role": member.role}
            )
    return online


def _music_key(room_id: str) -> str:
    return f"room_music:{room_id}"


def _music_queue_key(room_id: str) -> str:
    return f"room_music_queue:{room_id}"


async def music_snapshot(redis, room_id: str) -> dict | None:
    """Current room-music state, if any is playing - same role as
    presence_snapshot: read fresh on every connect so a late joiner or a
    reconnect gets caught up, not just whoever was already listening when
    the room-wide broadcast went out."""
    raw = await redis.get(_music_key(room_id))
    if raw is None:
        return None
    try:
        return json.loads(_decode(raw))
    except (TypeError, ValueError):
        return None


async def music_queue_snapshot(redis, room_id: str) -> list[dict]:
    raw_items = await redis.lrange(_music_queue_key(room_id), 0, -1)
    queue = []
    for raw in raw_items:
        try:
            queue.append(json.loads(_decode(raw)))
        except (TypeError, ValueError):
            continue
    return queue


# ---- Video call presence ----
# A "call" is an ephemeral, invite-based meeting identified by a random
# call_id - never just "the room's call". Without a distinct identity per
# meeting, two people who each clicked a generic "join call" button had no
# way to confirm they'd land in the same session (and sometimes didn't).
# call_id, handed out by handle_start_call and carried in every invite, is
# what two clients agree on to know they're joining each other specifically.


def _call_key(call_id: str) -> str:
    return f"call_presence:{call_id}"


def _member_calls_key(member_id: str) -> str:
    return f"member_active_calls:{member_id}"


async def call_presence_snapshot(redis, call_id: str) -> list[str]:
    raw_ids = await redis.smembers(_call_key(call_id))
    return [_decode(v) for v in raw_ids]


async def active_calls_for_member(redis, member_id: str) -> list[dict]:
    """Calls this member is currently part of, for the connect-time
    snapshot - same role as presence_snapshot/music_snapshot: a reconnect
    shouldn't lose track of a call you were already in."""
    raw_ids = await redis.smembers(_member_calls_key(member_id))
    calls = []
    for raw in raw_ids:
        call_id = _decode(raw)
        member_ids = await call_presence_snapshot(redis, call_id)
        if member_ids:
            calls.append({"call_id": call_id, "member_ids": member_ids})
    return calls


async def _publish_call_presence(redis, hub, room_id: str, call_id: str) -> None:
    member_ids = await call_presence_snapshot(redis, call_id)
    await hub.publish(room_id, {"type": "call_presence", "call_id": call_id, "member_ids": member_ids})


async def _join_call(redis, hub, settings, room_id: str, call_id: str, member_id: str) -> None:
    await redis.sadd(_call_key(call_id), member_id)
    await redis.expire(_call_key(call_id), settings.CALL_TTL_SECONDS)
    await redis.sadd(_member_calls_key(member_id), call_id)
    await redis.expire(_member_calls_key(member_id), settings.CALL_TTL_SECONDS)
    await _publish_call_presence(redis, hub, room_id, call_id)


async def _leave_call(redis, hub, room_id: str, call_id: str, member_id: str) -> None:
    await redis.srem(_call_key(call_id), member_id)
    await redis.srem(_member_calls_key(member_id), call_id)
    await _publish_call_presence(redis, hub, room_id, call_id)


async def cleanup_call_presence_on_disconnect(redis, hub, room_id: str, member_id: str) -> None:
    """Mirrors hub.presence_remove on disconnect - a dropped connection
    (tab closed, network loss) never gets a chance to send leave_call, so
    without this a departed member would linger in every call they were
    part of forever."""
    raw_ids = await redis.smembers(_member_calls_key(member_id))
    for raw in raw_ids:
        call_id = _decode(raw)
        removed = await redis.srem(_call_key(call_id), member_id)
        if removed:
            await _publish_call_presence(redis, hub, room_id, call_id)
    await redis.delete(_member_calls_key(member_id))


# ---- Game spectators ----
# Watching is ephemeral connection-based presence (same shape as call
# presence above) layered on top of a game, which is itself durable
# (Postgres). Losing your watcher registration on disconnect is fine -
# unlike a dropped call, nothing about the game itself depends on it.


def _watchers_key(game_id: str) -> str:
    return f"game_watchers:{game_id}"


def _member_watching_key(member_id: str) -> str:
    return f"member_watching_games:{member_id}"


async def watchers_snapshot(redis, game_id: str) -> list[str]:
    raw_ids = await redis.smembers(_watchers_key(game_id))
    return [_decode(v) for v in raw_ids]


async def _publish_watcher_count(redis, hub, room_id: str, game_id: str) -> None:
    count = len(await watchers_snapshot(redis, game_id))
    await hub.publish(room_id, {"type": "game_watchers", "game_id": game_id, "count": count})


async def _watch_game(redis, hub, settings, room_id: str, game_id: str, member_id: str) -> None:
    await redis.sadd(_watchers_key(game_id), member_id)
    await redis.expire(_watchers_key(game_id), settings.GAME_WATCH_TTL_SECONDS)
    await redis.sadd(_member_watching_key(member_id), game_id)
    await redis.expire(_member_watching_key(member_id), settings.GAME_WATCH_TTL_SECONDS)
    await _publish_watcher_count(redis, hub, room_id, game_id)


async def _unwatch_game(redis, hub, room_id: str, game_id: str, member_id: str) -> None:
    await redis.srem(_watchers_key(game_id), member_id)
    await redis.srem(_member_watching_key(member_id), game_id)
    await _publish_watcher_count(redis, hub, room_id, game_id)


async def cleanup_watchers_on_disconnect(redis, hub, room_id: str, member_id: str) -> None:
    """Mirrors cleanup_call_presence_on_disconnect - a tab closing never
    gets to send unwatch_game, so without this a departed spectator would
    count forever in every game they were watching."""
    raw_ids = await redis.smembers(_member_watching_key(member_id))
    for raw in raw_ids:
        game_id = _decode(raw)
        removed = await redis.srem(_watchers_key(game_id), member_id)
        if removed:
            await _publish_watcher_count(redis, hub, room_id, game_id)
    await redis.delete(_member_watching_key(member_id))


async def _broadcast_game_state(session, redis, hub, settings, room, game) -> None:
    """Builds and sends a per-recipient game_state to both players and
    every watcher, looked up fresh each time rather than kept in the
    event - a watcher list can change between moves. For almost every
    kind build_state_event produces the exact same dict regardless of
    who's asking, so this just costs a few extra cheap, in-memory
    rebuilds - only a hidden-information kind like battleship actually
    needs different payloads per recipient (see build_state_event's
    viewer_member_id and GameEngine.redact_for_viewer).

    Every delivery also refreshes that watcher's TTL. The TTL exists only
    as a safety net for a tab that vanished without sending unwatch_game
    (cleanup_watchers_on_disconnect handles the normal case) - without
    this refresh, a real game that runs longer than GAME_WATCH_TTL_SECONDS
    would silently drop every spectator mid-game: they'd stop receiving
    moves with no error, looking "stuck" until they re-watch by hand."""
    white_state = await games_mod.build_state_event(session, game, game.white_member_id)
    await hub.publish(room.id, white_state, to_member_id=game.white_member_id)
    if game.black_member_id is not None:
        black_state = await games_mod.build_state_event(session, game, game.black_member_id)
        await hub.publish(room.id, black_state, to_member_id=game.black_member_id)
    for watcher_id in await watchers_snapshot(redis, game.id):
        if watcher_id in (game.white_member_id, game.black_member_id):
            continue
        watcher_state = await games_mod.build_state_event(session, game, watcher_id)
        await hub.publish(room.id, watcher_state, to_member_id=watcher_id)
        await redis.expire(_watchers_key(game.id), settings.GAME_WATCH_TTL_SECONDS)
        await redis.expire(_member_watching_key(watcher_id), settings.GAME_WATCH_TTL_SECONDS)


async def post_system_message(session, settings, hub, room, text: str) -> None:
    """A WhatsApp-style "X joined"/"X left" notice: a real, persisted
    message (kind="system") in the room's general channel, so it shows up
    in history too, not just live for whoever's currently connected."""
    result = await session.execute(
        select(Channel).where(Channel.room_id == room.id, Channel.name == "general")
    )
    channel = result.scalar_one_or_none()
    if channel is None:
        return
    msg = await messages_mod.create_message(session, settings, channel, None, text=text, kind="system")
    await hub.publish(room.id, message_event(msg, None))


def message_event(msg: Message, from_name: str | None, client_id: str | None = None) -> dict:
    return {
        "type": "message",
        "channel_id": msg.channel_id,
        "id": msg.id,
        "seq": msg.seq,
        "member_id": msg.member_id,
        "from_name": from_name,
        "kind": msg.kind,
        "text": msg.text,
        "file_id": msg.file_id,
        "client_id": client_id,
        "created_at": msg.created_at.isoformat(),
    }


async def _get_channel_in_room(session, room_id: str, channel_id: str) -> Channel:
    channel = await session.get(Channel, channel_id)
    if channel is None or channel.room_id != room_id:
        raise DomainError("bad_request", "Unknown channel.")
    return channel


async def _get_target_member(session, room_id: str, member_id: str) -> Member:
    target = await session.get(Member, member_id)
    if target is None or target.room_id != room_id:
        raise DomainError("bad_request", "Unknown member.")
    return target


async def handle_send_message(session, settings, redis, hub, room, actor, data):
    from app import safety

    await safety.check_message_rate(redis, settings, actor.id)
    channel = await _get_channel_in_room(session, room.id, data.get("channel_id"))
    msg = await messages_mod.create_message(session, settings, channel, actor, text=data.get("text"))
    event = message_event(msg, actor.display_name, data.get("client_id"))
    await hub.publish(room.id, event)


async def handle_delete_message(session, settings, redis, hub, room, actor, data):
    message = await session.get(Message, data.get("message_id"))
    if message is None:
        raise DomainError("bad_request", "Unknown message.")
    channel = await _get_channel_in_room(session, room.id, message.channel_id)
    await messages_mod.delete_message(session, actor, message)
    await hub.publish(
        room.id, {"type": "message_deleted", "channel_id": channel.id, "message_id": message.id}
    )


async def _publish_pins(session, hub, room):
    pins = await messages_mod.list_pins(session, room.id)
    await hub.publish(room.id, {"type": "pins", "message_ids": [p.message_id for p in pins]})


async def handle_pin(session, settings, redis, hub, room, actor, data):
    message = await session.get(Message, data.get("message_id"))
    if message is None:
        raise DomainError("bad_request", "Unknown message.")
    await messages_mod.pin_message(session, settings, room.id, actor, message)
    await _publish_pins(session, hub, room)


async def handle_unpin(session, settings, redis, hub, room, actor, data):
    await messages_mod.unpin_message(session, room.id, actor, data.get("message_id"))
    await _publish_pins(session, hub, room)


async def _publish_presence(session, redis, hub, room):
    online = await presence_snapshot(session, redis, room.id)
    await hub.publish(room.id, {"type": "presence", "online": online})


async def handle_approve_member(session, settings, redis, hub, room, actor, data):
    target = await _get_target_member(session, room.id, data.get("member_id"))
    target = await members_mod.approve_member(session, actor, target)
    await hub.publish(room.id, {"type": "member_joined", "member_id": target.id, "name": target.display_name})
    await post_system_message(session, settings, hub, room, f"{target.display_name} joined")
    await _publish_presence(session, redis, hub, room)


async def handle_reject_member(session, settings, redis, hub, room, actor, data):
    target = await _get_target_member(session, room.id, data.get("member_id"))
    await members_mod.reject_member(session, actor, target)
    await hub.publish(
        room.id,
        {"type": "removed", "reason": "Your join request was declined."},
        to_member_id=target.id,
        close_after=True,
    )


async def handle_remove_member(session, settings, redis, hub, room, actor, data):
    target = await _get_target_member(session, room.id, data.get("member_id"))
    await members_mod.remove_member(session, actor, target)
    await hub.publish(
        room.id,
        {"type": "removed", "reason": "You were removed from this room."},
        to_member_id=target.id,
        close_after=True,
    )
    await hub.publish(room.id, {"type": "member_left", "member_id": target.id})
    await hub.presence_remove(room.id, target.id)
    await post_system_message(session, settings, hub, room, f"{target.display_name} left")
    await _publish_presence(session, redis, hub, room)


async def handle_ban_member(session, settings, redis, hub, room, actor, data):
    target = await _get_target_member(session, room.id, data.get("member_id"))
    await members_mod.ban_member(session, actor, target)
    await hub.publish(
        room.id,
        {"type": "removed", "reason": "You were banned from this room."},
        to_member_id=target.id,
        close_after=True,
    )
    await hub.publish(room.id, {"type": "member_left", "member_id": target.id})
    await hub.presence_remove(room.id, target.id)
    await post_system_message(session, settings, hub, room, f"{target.display_name} left")
    await _publish_presence(session, redis, hub, room)


async def handle_set_role(session, settings, redis, hub, room, actor, data):
    target = await _get_target_member(session, room.id, data.get("member_id"))
    role = data.get("role")
    await members_mod.set_role(session, actor, target, role)
    await hub.publish(room.id, {"type": "role_changed", "member_id": target.id, "role": role})
    await _publish_presence(session, redis, hub, room)


async def handle_offer_ownership(session, settings, redis, hub, room, actor, data):
    if actor.role != "owner":
        raise DomainError("not_allowed", "Only the owner can hand over ownership.")
    target = await _get_target_member(session, room.id, data.get("member_id"))
    if target.status != "active" or target.id == actor.id:
        raise DomainError("bad_request", "Can't offer ownership to that member.")
    hub.pending_offers[room.id] = target.id
    await hub.publish(
        room.id, {"type": "ownership_offer", "from_name": actor.display_name}, to_member_id=target.id
    )


async def handle_answer_ownership(session, settings, redis, hub, room, actor, data):
    pending_id = hub.pending_offers.get(room.id)
    if pending_id != actor.id:
        raise DomainError("bad_request", "You don't have a pending ownership offer.")

    if not data.get("accept"):
        del hub.pending_offers[room.id]
        return

    del hub.pending_offers[room.id]
    old_owner = await session.get(Member, room.owner_member_id)
    await rooms_mod.transfer_ownership(session, room, old_owner, actor)
    await hub.publish(
        room.id,
        {
            "type": "ownership_changed",
            "new_owner_id": actor.id,
            "message": f"{actor.display_name} is now the owner of this room.",
        },
    )
    await _publish_presence(session, redis, hub, room)


async def handle_create_channel(session, settings, redis, hub, room, actor, data):
    channel = await messages_mod.create_channel(session, settings, room, actor, data.get("name"))
    await hub.publish(room.id, {"type": "channel_created", "channel_id": channel.id, "name": channel.name})


async def handle_rename(session, settings, redis, hub, room, actor, data):
    await members_mod.rename_member(session, actor, data.get("display_name"), settings)
    await _publish_presence(session, redis, hub, room)


MUSIC_QUEUE_MAX = 25


async def _resolve_track(session, settings, room, data: dict) -> dict:
    library_track_id = data.get("library_track_id")
    file_id = data.get("file_id")

    if library_track_id:
        track = music_library.get_track(library_track_id)
        if track is None:
            raise DomainError("bad_request", "Unknown library track.")
        return {
            "source": "library",
            "url": track["url"],
            "filename": track["title"],
            "attribution": f'{track["artist"]} · {track["license"]}',
        }
    if file_id:
        asset = await files_mod.get_file_or_404(session, room.id, file_id)
        if files_mod.file_extension(asset.filename) not in settings.MUSIC_EXTENSIONS:
            raise DomainError("file_type", "That file isn't a playable audio file.")
        return {"source": "upload", "file_id": asset.id, "filename": asset.filename}
    raise DomainError("bad_request", "No file specified.")


async def _save_queue(redis, settings, room_id: str, queue: list[dict]) -> None:
    await redis.delete(_music_queue_key(room_id))
    if queue:
        await redis.rpush(_music_queue_key(room_id), *[json.dumps(t) for t in queue])
        await redis.expire(_music_queue_key(room_id), settings.ROOM_MUSIC_TTL_SECONDS)


async def _publish_music_queue(redis, hub, room_id: str) -> list[dict]:
    queue = await music_queue_snapshot(redis, room_id)
    await hub.publish(room_id, {"type": "music_queue_updated", "queue": queue})
    return queue


async def _advance_music(redis, settings, hub, room) -> None:
    """One track's turn is over (it was stopped, or finished on its own) -
    promote the next queued one to "now playing", or clear entirely if the
    queue's empty. Shared by the manual-stop and natural-end paths, which
    both just mean "this one's done, move on"."""
    queue = await music_queue_snapshot(redis, room.id)
    if not queue:
        await redis.delete(_music_key(room.id))
        await hub.publish(room.id, {"type": "music_stopped"})
        return

    next_track, *rest = queue
    next_track["started_by_member_id"] = next_track.pop("requested_by_member_id")
    next_track["started_by_name"] = next_track.pop("requested_by_name")
    next_track.pop("queued_at_ms", None)
    next_track["started_at_ms"] = int(time.time() * 1000)

    await redis.set(_music_key(room.id), json.dumps(next_track), ex=settings.ROOM_MUSIC_TTL_SECONDS)
    await hub.publish(room.id, {"type": "music_started", **next_track})
    await _save_queue(redis, settings, room.id, rest)
    await _publish_music_queue(redis, hub, room.id)


async def handle_start_music(session, settings, redis, hub, room, actor, data):
    # No role check, same reasoning as handle_start_call - picking a song
    # for the room is a normal member action, not a mod/owner privilege.
    track = await _resolve_track(session, settings, room, data)
    track["id"] = new_id()

    current = await music_snapshot(redis, room.id)
    if current is None or current.get("started_by_member_id") == actor.id:
        # Nothing playing, or it's your own track - swap it right away.
        # There's no one to queue behind when it's your own pick replacing
        # itself, so this doesn't touch the queue at all.
        track["started_by_member_id"] = actor.id
        track["started_by_name"] = actor.display_name
        track["started_at_ms"] = int(time.time() * 1000)
        await redis.set(_music_key(room.id), json.dumps(track), ex=settings.ROOM_MUSIC_TTL_SECONDS)
        await hub.publish(room.id, {"type": "music_started", **track})
        return

    # Someone else's song is already playing - this joins the queue
    # instead of cutting them off. One person, one queued slot at a time:
    # picking a second song while you already have one waiting replaces
    # it rather than piling up, so you can't just flood the line.
    queue = [t for t in await music_queue_snapshot(redis, room.id) if t.get("requested_by_member_id") != actor.id]
    if len(queue) >= MUSIC_QUEUE_MAX:
        raise DomainError("bad_request", "The queue's full right now - try again once it clears up.")

    track["requested_by_member_id"] = actor.id
    track["requested_by_name"] = actor.display_name
    track["queued_at_ms"] = int(time.time() * 1000)
    queue.append(track)
    await _save_queue(redis, settings, room.id, queue)
    await _publish_music_queue(redis, hub, room.id)

    # A direct, targeted heads-up to whoever's currently playing - not a
    # demand, just "someone's waiting whenever you're ready to pass it on".
    await hub.publish(
        room.id,
        {
            "type": "music_requested",
            "filename": track["filename"],
            "requested_by_member_id": actor.id,
            "requested_by_name": actor.display_name,
        },
        to_member_id=current.get("started_by_member_id"),
    )


async def handle_stop_music(session, settings, redis, hub, room, actor, data):
    """A deliberate, manual skip - only whoever's track is currently
    playing (or a moderator, as a safety net) can cut it short. This is
    what "I'll cancel mine so yours can play" actually calls."""
    current = await music_snapshot(redis, room.id)
    if current is None:
        return
    if actor.id != current.get("started_by_member_id") and actor.role not in ("owner", "mod"):
        raise DomainError("not_allowed", "Only whoever started this song (or a moderator) can stop it.")
    await _advance_music(redis, settings, hub, room)


async def handle_music_track_ended(session, settings, redis, hub, room, actor, data):
    """A track finishing on its own isn't "stopping someone's music" - any
    listener's own <audio> element firing onEnded can report it, no
    permission needed. track_id guards against several listeners' audio
    elements all ending around the same moment and each independently
    trying to advance - only the first report (for whichever track is
    still actually current) does anything; the rest are no-ops."""
    current = await music_snapshot(redis, room.id)
    if current is None:
        return
    if data.get("track_id") and data.get("track_id") != current.get("id"):
        return
    await _advance_music(redis, settings, hub, room)


async def handle_cancel_queued_music(session, settings, redis, hub, room, actor, data):
    track_id = data.get("track_id")
    if not track_id:
        raise DomainError("bad_request", "Missing track_id.")

    queue = await music_queue_snapshot(redis, room.id)
    target = next((t for t in queue if t.get("id") == track_id), None)
    if target is None:
        raise DomainError("bad_request", "That queued track isn't there anymore.")
    if actor.id != target.get("requested_by_member_id") and actor.role not in ("owner", "mod"):
        raise DomainError("not_allowed", "Only whoever queued this (or a moderator) can remove it.")

    queue = [t for t in queue if t.get("id") != track_id]
    await _save_queue(redis, settings, room.id, queue)
    await _publish_music_queue(redis, hub, room.id)


async def handle_start_call(session, settings, redis, hub, room, actor, data):
    # No role check, same as sending a message - starting a call is a
    # normal member action, not a mod/owner privilege.
    invitee_ids = data.get("invitee_ids")
    if not isinstance(invitee_ids, list) or not invitee_ids:
        raise DomainError("bad_request", "Pick at least one person to invite.")

    invitees = []
    for member_id in invitee_ids:
        target = await session.get(Member, member_id)
        if target is None or target.room_id != room.id or target.status != "active":
            raise DomainError("bad_request", "Invalid invitee.")
        invitees.append(target)

    call_id = new_id()
    await _join_call(redis, hub, settings, room.id, call_id, actor.id)

    invite = {
        "type": "call_invite",
        "call_id": call_id,
        "host_member_id": actor.id,
        "host_name": actor.display_name,
    }
    # Published once per target rather than broadcast - this is a ring,
    # not a room-wide announcement, so only invitees (and the host, who
    # needs the same event to learn their own new call_id) see it.
    for target in invitees:
        await hub.publish(room.id, invite, to_member_id=target.id)
    await hub.publish(room.id, invite, to_member_id=actor.id)


async def handle_join_call(session, settings, redis, hub, room, actor, data):
    call_id = data.get("call_id")
    if not call_id:
        raise DomainError("bad_request", "Missing call_id.")
    await _join_call(redis, hub, settings, room.id, call_id, actor.id)


async def handle_leave_call(session, settings, redis, hub, room, actor, data):
    call_id = data.get("call_id")
    if not call_id:
        raise DomainError("bad_request", "Missing call_id.")
    await _leave_call(redis, hub, room.id, call_id, actor.id)


async def _relay_to_peer(hub, room, actor, data, event_type: str, payload_key: str) -> None:
    target_id = data.get("to_member_id")
    payload = data.get(payload_key)
    if not target_id or payload is None:
        raise DomainError("bad_request", f"Missing to_member_id or {payload_key}.")
    await hub.publish(
        room.id,
        {"type": event_type, "from_member_id": actor.id, payload_key: payload},
        to_member_id=target_id,
    )


async def handle_call_offer(session, settings, redis, hub, room, actor, data):
    await _relay_to_peer(hub, room, actor, data, "call_offer", "sdp")


async def handle_call_answer(session, settings, redis, hub, room, actor, data):
    await _relay_to_peer(hub, room, actor, data, "call_answer", "sdp")


async def handle_call_ice_candidate(session, settings, redis, hub, room, actor, data):
    await _relay_to_peer(hub, room, actor, data, "ice_candidate", "candidate")


# ---- Games (chess, the first) ----
# One pending-or-active game per member per room at a time (see
# games.get_live_game_for_member) - keeps the frontend's state to a single
# myGameId slot, same shape as myCallId, instead of a list.

async def handle_challenge_game(session, settings, redis, hub, room, actor, data):
    kind = data.get("kind", "chess")
    opponent = await _get_target_member(session, room.id, data.get("opponent_id"))
    game = await games_mod.create_challenge(session, room, actor, opponent, kind=kind)
    invite = games_mod.invite_event(game, actor, opponent)
    # Sent to both - the challenger needs the same event to learn the new
    # game_id and show a "waiting for a reply" state, same pattern as
    # handle_start_call echoing call_invite back to its own host.
    await hub.publish(room.id, invite, to_member_id=opponent.id)
    await hub.publish(room.id, invite, to_member_id=actor.id)


async def handle_challenge_to_chess(session, settings, redis, hub, room, actor, data):
    """Legacy alias - keeps the old wire message name (and every
    test_chess.py call site) working verbatim. New frontend code for every
    kind, chess included, sends challenge_game with an explicit kind."""
    await handle_challenge_game(session, settings, redis, hub, room, actor, {**data, "kind": "chess"})


async def handle_accept_game(session, settings, redis, hub, room, actor, data):
    game = await games_mod.get_game_or_404(session, room.id, data.get("game_id"))
    game = await games_mod.accept_challenge(session, game, actor)
    await _broadcast_game_state(session, redis, hub, settings, room, game)
    # Room-wide (no to_member_id) - everyone else gets a lightweight
    # "live now" banner they can tap to spectate, without being dropped
    # into the board themselves.
    white = await session.get(Member, game.white_member_id)
    black = await session.get(Member, game.black_member_id)
    await hub.publish(room.id, games_mod.live_event(game, white, black))
    label = _game_label(game.kind)
    await post_system_message(
        session, settings, hub, room,
        f"{label['emoji']} {white.display_name} and {black.display_name} started a game of {label['name']}!",
    )


async def handle_decline_game(session, settings, redis, hub, room, actor, data):
    game = await games_mod.get_game_or_404(session, room.id, data.get("game_id"))
    white_id = game.white_member_id
    game = await games_mod.decline_challenge(session, game, actor)
    await hub.publish(room.id, {"type": "game_declined", "game_id": game.id}, to_member_id=white_id)


async def handle_cancel_game(session, settings, redis, hub, room, actor, data):
    game = await games_mod.get_game_or_404(session, room.id, data.get("game_id"))
    black_id = game.black_member_id
    game = await games_mod.cancel_challenge(session, game, actor)
    # black_id is None for an awaiting link-challenge nobody's claimed yet
    # - hub.publish treats a missing to_member_id as room-wide, so skip
    # the notification entirely rather than broadcasting it to everyone.
    if black_id is not None:
        await hub.publish(room.id, {"type": "game_cancelled", "game_id": game.id}, to_member_id=black_id)


async def handle_create_game_link(session, settings, redis, hub, room, actor, data):
    kind = data.get("kind", "chess")
    game = await games_mod.create_link_challenge(session, room, actor, kind=kind)
    await hub.publish(room.id, games_mod.link_waiting_event(game, actor), to_member_id=actor.id)


async def handle_claim_game_link(session, settings, redis, hub, room, actor, data):
    token = data.get("token")
    if not token:
        raise DomainError("bad_request", "Missing token.")
    game = await games_mod.get_game_by_token(session, room.id, token)
    if game is None:
        raise DomainError("bad_request", "That invite link isn't valid anymore.")
    game, is_fresh = await games_mod.claim_link_challenge(session, room, game, actor)
    if not is_fresh:
        # Re-opening the same link they already used - just resync them
        # into the game, no second "started a game" announcement/broadcast.
        state = await games_mod.build_state_event(session, game, actor.id)
        await hub.publish(room.id, state, to_member_id=actor.id)
        return
    await _broadcast_game_state(session, redis, hub, settings, room, game)
    white = await session.get(Member, game.white_member_id)
    await hub.publish(room.id, games_mod.live_event(game, white, actor))
    label = _game_label(game.kind)
    await post_system_message(
        session, settings, hub, room,
        f"{label['emoji']} {white.display_name} and {actor.display_name} started a game of {label['name']}!",
    )


async def handle_game_move(session, settings, redis, hub, room, actor, data):
    game = await games_mod.get_game_or_404(session, room.id, data.get("game_id"))
    engine = games_mod.get_engine(game.kind)
    try:
        move = engine.parse_move(data)
    except (KeyError, ValueError, TypeError):
        raise DomainError("bad_request", "Missing or invalid move.")
    game = await games_mod.apply_move(session, game, actor, move)
    await _broadcast_game_state(session, redis, hub, settings, room, game)
    if game.status == "finished":
        white = await session.get(Member, game.white_member_id)
        black = await session.get(Member, game.black_member_id)
        await hub.publish(room.id, {"type": "game_live_ended", "game_id": game.id})
        await post_system_message(session, settings, hub, room, _result_message(game, white, black))


async def handle_resign_game(session, settings, redis, hub, room, actor, data):
    game = await games_mod.get_game_or_404(session, room.id, data.get("game_id"))
    game = await games_mod.resign(session, game, actor)
    await _broadcast_game_state(session, redis, hub, settings, room, game)
    white = await session.get(Member, game.white_member_id)
    black = await session.get(Member, game.black_member_id)
    await hub.publish(room.id, {"type": "game_live_ended", "game_id": game.id})
    await post_system_message(session, settings, hub, room, _result_message(game, white, black))


async def handle_watch_game(session, settings, redis, hub, room, actor, data):
    game = await games_mod.get_game_or_404(session, room.id, data.get("game_id"))
    await _watch_game(redis, hub, settings, room.id, game.id, actor.id)
    # The watcher needs the current board immediately, not just future
    # moves - a direct send, same reasoning as the connect-time snapshot.
    # actor.id won't match either seat, so this naturally resolves to the
    # spectator-safe view for a hidden-information kind.
    state = await games_mod.build_state_event(session, game, actor.id)
    await hub.publish(room.id, state, to_member_id=actor.id)


async def handle_unwatch_game(session, settings, redis, hub, room, actor, data):
    game_id = data.get("game_id")
    if not game_id:
        raise DomainError("bad_request", "Missing game_id.")
    await _unwatch_game(redis, hub, room.id, game_id, actor.id)


GAME_LABELS: dict[str, dict[str, str]] = {
    "chess": {"emoji": "♟️", "name": "chess"},
    "tictactoe": {"emoji": "⭕", "name": "tic-tac-toe"},
    "connect4": {"emoji": "🔴", "name": "Connect Four"},
}


def _game_label(kind: str) -> dict[str, str]:
    return GAME_LABELS.get(kind, {"emoji": "🎮", "name": kind})


def _result_message(game, white: Member, black: Member) -> str:
    label = _game_label(game.kind)
    white_name, black_name = white.display_name, black.display_name
    termination = (game.termination or "").replace("_", " ")
    if game.result == "draw":
        return f"{label['emoji']} {white_name} and {black_name}'s {label['name']} game ended in a draw ({termination})."
    winner = white_name if game.result == "white" else black_name
    loser = black_name if game.result == "white" else white_name
    if game.termination == "resignation":
        return f"{label['emoji']} {winner} wins! {loser} resigned."
    if game.kind == "chess" and game.termination == "checkmate":
        return f"{label['emoji']} Checkmate! {winner} wins the {label['name']} game."
    return f"{label['emoji']} {winner} wins the {label['name']} game ({termination})."


# ---- Party games (trivia, the first) ----
# N arbitrary room participants in a host-started lobby, not the 2-seat
# board-game model above - see app/party_engines/base.py. One live party
# game per ROOM at a time (not per-member like board games).

PARTY_REVEAL_PAUSE_SECONDS = 5

PARTY_GAME_LABELS: dict[str, dict[str, str]] = {
    "trivia": {"emoji": "🧠", "name": "Trivia Night"},
    "draft": {"emoji": "🃏", "name": "Card Draft"},
    "uno": {"emoji": "🔴", "name": "Uno"},
    "codenames": {"emoji": "🕵️", "name": "Codenames"},
    "hearts": {"emoji": "♥️", "name": "Hearts"},
    "werewolf": {"emoji": "🐺", "name": "Werewolf"},
    "spades": {"emoji": "♠️", "name": "Spades"},
}


def _party_game_label(kind: str) -> dict[str, str]:
    return PARTY_GAME_LABELS.get(kind, {"emoji": "🎉", "name": kind})


def _party_result_message(party_game, scoreboard: list[dict]) -> str:
    label = _party_game_label(party_game.kind)
    if not scoreboard:
        return f"{label['emoji']} {label['name']} has ended."
    winner = scoreboard[0]
    return f"{label['emoji']} {winner['name']} wins {label['name']} with {winner['score']} points!"


async def _broadcast_party_state(session, redis, hub, room, party_game) -> None:
    """Sends each participant their OWN build_state_event - the N-player
    analogue of _broadcast_game_state. Needed because "my_answer" is
    viewer-specific even though the rest of the payload is identical for
    everyone; using this same per-viewer loop for the reveal phase too
    (where nothing is secret anymore) trades a few extra cheap rebuilds
    for one code path, same tradeoff _broadcast_game_state already makes
    for itself. While status=="lobby" this also room-broadcasts once so
    non-participants can discover and join it."""
    if party_game.status == "lobby":
        event = await party_games_mod.build_state_event(session, party_game)
        await hub.publish(room.id, event)
        return
    for member_id in json.loads(party_game.participants_json):
        event = await party_games_mod.build_state_event(session, party_game, member_id)
        await hub.publish(room.id, event, to_member_id=member_id)


async def _advance_or_finish_party_round(session, settings, redis, hub, room, party_game) -> None:
    """THE one place a round ends - called by the server timer firing, by
    every participant answering early, or by the host's skip action.
    Idempotent against the timer and an early-finish racing each other
    (two different DB sessions both reaching here around the same
    instant): party_games.time_up -> engine.time_up only does real work
    if the round hasn't already been revealed; a second caller that
    loses the race just re-broadcasts the already-current reveal - same
    "only the first report does anything, the rest are no-ops" tolerance
    handle_music_track_ended already documents for itself."""
    hub.cancel_party_timer(party_game.id)
    party_game, game_over = await party_games_mod.time_up(session, party_game)
    await _broadcast_party_state(session, redis, hub, room, party_game)

    if game_over:
        final = await party_games_mod.build_state_event(session, party_game)
        await post_system_message(
            session, settings, hub, room, _party_result_message(party_game, final["scoreboard"])
        )
        return

    hub.schedule_party_timer(
        party_game.id,
        PARTY_REVEAL_PAUSE_SECONDS,
        lambda: _handle_reveal_pause_elapsed(hub, settings, room.id, party_game.id),
    )


async def _handle_reveal_pause_elapsed(hub, settings, room_id: str, party_game_id: str) -> None:
    if hub.db is None:
        return
    async with hub.db.session() as session:
        try:
            party_game = await session.get(PartyGame, party_game_id)
            room = await session.get(Room, room_id)
            if party_game is None or party_game.status != "active" or room is None or not room.is_active():
                return
            party_game, duration = await party_games_mod.advance_round(session, party_game)
            await _broadcast_party_state(session, hub.redis, hub, room, party_game)
            hub.schedule_party_timer(
                party_game.id,
                duration,
                lambda: _handle_round_timeout(hub, settings, room.id, party_game.id),
            )
        except Exception:
            pass  # must never crash the Hub's listener loop or another live timer


async def _handle_round_timeout(hub, settings, room_id: str, party_game_id: str) -> None:
    if hub.db is None:
        return
    async with hub.db.session() as session:
        try:
            party_game = await session.get(PartyGame, party_game_id)
            room = await session.get(Room, room_id)
            if party_game is None or party_game.status != "active" or room is None or not room.is_active():
                return
            await _advance_or_finish_party_round(session, settings, hub.redis, hub, room, party_game)
        except Exception:
            pass


async def handle_start_party_game(session, settings, redis, hub, room, actor, data):
    party_game = await party_games_mod.create_lobby(session, room, actor, kind=data.get("kind", "trivia"))
    await _broadcast_party_state(session, redis, hub, room, party_game)


async def handle_join_party_game(session, settings, redis, hub, room, actor, data):
    party_game = await party_games_mod.get_party_game_or_404(session, room.id, data.get("party_game_id"))
    party_game = await party_games_mod.join_lobby(session, party_game, actor)
    await _broadcast_party_state(session, redis, hub, room, party_game)


async def handle_leave_party_game(session, settings, redis, hub, room, actor, data):
    party_game = await party_games_mod.get_party_game_or_404(session, room.id, data.get("party_game_id"))
    party_game = await party_games_mod.leave_lobby(session, party_game, actor)
    await _broadcast_party_state(session, redis, hub, room, party_game)


async def handle_begin_party_game(session, settings, redis, hub, room, actor, data):
    party_game = await party_games_mod.get_party_game_or_404(session, room.id, data.get("party_game_id"))
    party_game, duration = await party_games_mod.start_game(session, party_game, actor)
    await _broadcast_party_state(session, redis, hub, room, party_game)
    hub.schedule_party_timer(
        party_game.id, duration, lambda: _handle_round_timeout(hub, settings, room.id, party_game.id)
    )
    label = _party_game_label(party_game.kind)
    n = len(json.loads(party_game.participants_json))
    await post_system_message(
        session, settings, hub, room,
        f"{label['emoji']} {actor.display_name} started a game of {label['name']} with {n} players!",
    )


async def handle_party_action(session, settings, redis, hub, room, actor, data):
    party_game = await party_games_mod.get_party_game_or_404(session, room.id, data.get("party_game_id"))
    engine = party_games_mod.get_party_engine(party_game.kind)
    try:
        action = engine.parse_action(data)
    except (KeyError, ValueError, TypeError):
        raise DomainError("bad_request", "Missing or invalid action.")
    party_game, round_over = await party_games_mod.submit_answer(session, party_game, actor, action)
    await _broadcast_party_state(session, redis, hub, room, party_game)
    if round_over:
        await _advance_or_finish_party_round(session, settings, redis, hub, room, party_game)


async def handle_skip_party_round(session, settings, redis, hub, room, actor, data):
    party_game = await party_games_mod.get_party_game_or_404(session, room.id, data.get("party_game_id"))
    await party_games_mod.skip_round(session, party_game, actor)  # permission check only
    await _advance_or_finish_party_round(session, settings, redis, hub, room, party_game)


async def handle_cancel_party_game(session, settings, redis, hub, room, actor, data):
    party_game = await party_games_mod.get_party_game_or_404(session, room.id, data.get("party_game_id"))
    hub.cancel_party_timer(party_game.id)
    party_game = await party_games_mod.cancel_game(session, party_game, actor)
    await hub.publish(room.id, {"type": "party_cancelled", "party_game_id": party_game.id})


async def cleanup_party_lobby_on_disconnect(session, settings, hub, room_id: str, member_id: str) -> None:
    """Only matters pre-start - once active, the roster is locked and the
    round timer is authoritative regardless of who's connected (same
    spirit as music's TTL-based tolerance), so this is a silent no-op for
    an active/finished game. If removing the last lobby participant
    empties the roster, auto-cancels the now-unreachable lobby rather
    than leaving a permanent "0 players" ghost nobody can ever start."""
    party_game = await party_games_mod.get_live_party_game_for_room(session, room_id)
    if party_game is None or party_game.status != "lobby":
        return
    member = await session.get(Member, member_id)
    room = await session.get(Room, room_id)
    if member is None or room is None:
        return
    party_game = await party_games_mod.leave_lobby(session, party_game, member)
    if not json.loads(party_game.participants_json):
        party_game.status = "cancelled"
        await session.commit()
        await hub.publish(room.id, {"type": "party_cancelled", "party_game_id": party_game.id})
        return
    await hub.publish(room.id, await party_games_mod.build_state_event(session, party_game))


# ---- Card games (poker, the first) ----
# A seated table of N players whose chip stacks persist across many hands
# in one sitting - closer in shape to party games (N participants, a
# lobby) than to the 2-seat board games, but with no round timer: a
# betting decision has no fixed length, so (unlike Trivia) nothing here
# advances on a clock - see app/card_engines/base.py.

CARD_GAME_LABELS: dict[str, dict[str, str]] = {
    "poker": {"emoji": "\U0001fa99", "name": "Poker"},
}


def _card_game_label(kind: str) -> dict[str, str]:
    return CARD_GAME_LABELS.get(kind, {"emoji": "\U0001f0cf", "name": kind})


async def _broadcast_card_state(session, redis, hub, room, card_game) -> None:
    """Sends each seated player their OWN build_state_event - hole cards
    are viewer-specific for the entire hand (not just until a reveal
    point the way Trivia's answers are), so there is no safe shared
    payload once a hand is active. Room-wide while status=="lobby" so the
    table is discoverable, same as PartyGame."""
    if card_game.status == "lobby":
        event = await card_games_mod.build_state_event(session, card_game)
        await hub.publish(room.id, event)
        return
    for member_id in json.loads(card_game.participants_json):
        event = await card_games_mod.build_state_event(session, card_game, member_id)
        await hub.publish(room.id, event, to_member_id=member_id)


async def _resolve_and_broadcast_hand(session, settings, redis, hub, room, card_game) -> None:
    card_game, game_over = await card_games_mod.resolve_hand(session, card_game)
    await _broadcast_card_state(session, redis, hub, room, card_game)

    state = json.loads(card_game.state_json)
    label = _card_game_label(card_game.kind)
    showdown = state.get("showdown")
    if showdown:
        winners = {w for p in (state.get("pot_summary") or []) for w in p["winners"]}
        if winners:
            names = []
            for member_id in winners:
                member = await session.get(Member, member_id)
                names.append(member.display_name if member else "Unknown")
            description = showdown.get(next(iter(winners)), {}).get("description", "")
            await post_system_message(
                session, settings, hub, room,
                f"{label['emoji']} {', '.join(names)} won the pot with {description}!",
            )
    if game_over:
        winner_id = max(state["chip_stacks"], key=lambda m: state["chip_stacks"][m])
        winner = await session.get(Member, winner_id)
        await post_system_message(
            session, settings, hub, room,
            f"{label['emoji']} {winner.display_name if winner else 'Someone'} won the whole table!",
        )


async def handle_start_card_game(session, settings, redis, hub, room, actor, data):
    starting_chips = data.get("starting_chips", card_games_mod.DEFAULT_STARTING_CHIPS)
    if not isinstance(starting_chips, int) or isinstance(starting_chips, bool) or not (10 <= starting_chips <= 1_000_000):
        raise DomainError("bad_request", "Invalid starting chip count.")
    card_game = await card_games_mod.create_lobby(
        session, room, actor, kind=data.get("kind", "poker"), starting_chips=starting_chips
    )
    await _broadcast_card_state(session, redis, hub, room, card_game)


async def handle_join_card_game(session, settings, redis, hub, room, actor, data):
    card_game = await card_games_mod.get_card_game_or_404(session, room.id, data.get("card_game_id"))
    card_game = await card_games_mod.join_lobby(session, card_game, actor)
    await _broadcast_card_state(session, redis, hub, room, card_game)


async def handle_leave_card_game(session, settings, redis, hub, room, actor, data):
    card_game = await card_games_mod.get_card_game_or_404(session, room.id, data.get("card_game_id"))
    card_game = await card_games_mod.leave_lobby(session, card_game, actor)
    await _broadcast_card_state(session, redis, hub, room, card_game)


async def handle_begin_card_game(session, settings, redis, hub, room, actor, data):
    card_game = await card_games_mod.get_card_game_or_404(session, room.id, data.get("card_game_id"))
    card_game = await card_games_mod.start_game(session, card_game, actor)
    await _broadcast_card_state(session, redis, hub, room, card_game)
    label = _card_game_label(card_game.kind)
    n = len(json.loads(card_game.participants_json))
    await post_system_message(
        session, settings, hub, room,
        f"{label['emoji']} {actor.display_name} started a game of {label['name']} with {n} players!",
    )


async def handle_card_action(session, settings, redis, hub, room, actor, data):
    card_game = await card_games_mod.get_card_game_or_404(session, room.id, data.get("card_game_id"))
    engine = card_games_mod.get_card_engine(card_game.kind)
    try:
        action = engine.parse_action(data)
    except (KeyError, ValueError, TypeError):
        raise DomainError("bad_request", "Missing or invalid action.")
    card_game, hand_over = await card_games_mod.submit_action(session, card_game, actor, action)
    await _broadcast_card_state(session, redis, hub, room, card_game)
    if hand_over:
        await _resolve_and_broadcast_hand(session, settings, redis, hub, room, card_game)


async def handle_start_next_hand(session, settings, redis, hub, room, actor, data):
    card_game = await card_games_mod.get_card_game_or_404(session, room.id, data.get("card_game_id"))
    card_game = await card_games_mod.start_next_hand(session, card_game, actor)
    await _broadcast_card_state(session, redis, hub, room, card_game)


async def handle_cancel_card_game(session, settings, redis, hub, room, actor, data):
    card_game = await card_games_mod.get_card_game_or_404(session, room.id, data.get("card_game_id"))
    card_game = await card_games_mod.cancel_game(session, card_game, actor)
    await hub.publish(room.id, {"type": "card_cancelled", "card_game_id": card_game.id})


async def cleanup_card_lobby_on_disconnect(session, settings, hub, room_id: str, member_id: str) -> None:
    """Mirrors cleanup_party_lobby_on_disconnect - only matters pre-start;
    once active, a seat is held (not vacated) regardless of connection,
    same as leave_lobby's own no-op-once-active behavior."""
    card_game = await card_games_mod.get_live_card_game_for_room(session, room_id)
    if card_game is None or card_game.status != "lobby":
        return
    member = await session.get(Member, member_id)
    room = await session.get(Room, room_id)
    if member is None or room is None:
        return
    card_game = await card_games_mod.leave_lobby(session, card_game, member)
    if not json.loads(card_game.participants_json):
        card_game.status = "cancelled"
        await session.commit()
        await hub.publish(room.id, {"type": "card_cancelled", "card_game_id": card_game.id})
        return
    await hub.publish(room.id, await card_games_mod.build_state_event(session, card_game))


async def handle_leave(session, settings, redis, hub, room, actor, data):
    display_name = actor.display_name
    await members_mod.leave_room(session, actor)
    await hub.publish(room.id, {"type": "member_left", "member_id": actor.id})
    await hub.presence_remove(room.id, actor.id)
    await post_system_message(session, settings, hub, room, f"{display_name} left")
    await _publish_presence(session, redis, hub, room)
    hub.unregister(room.id, actor.id)


HANDLERS = {
    "send_message": handle_send_message,
    "delete_message": handle_delete_message,
    "pin": handle_pin,
    "unpin": handle_unpin,
    "approve_member": handle_approve_member,
    "reject_member": handle_reject_member,
    "remove_member": handle_remove_member,
    "ban_member": handle_ban_member,
    "set_role": handle_set_role,
    "offer_ownership": handle_offer_ownership,
    "answer_ownership": handle_answer_ownership,
    "create_channel": handle_create_channel,
    "rename": handle_rename,
    "leave": handle_leave,
    "start_music": handle_start_music,
    "stop_music": handle_stop_music,
    "music_track_ended": handle_music_track_ended,
    "cancel_queued_music": handle_cancel_queued_music,
    "start_call": handle_start_call,
    "join_call": handle_join_call,
    "leave_call": handle_leave_call,
    "call_offer": handle_call_offer,
    "call_answer": handle_call_answer,
    "call_ice_candidate": handle_call_ice_candidate,
    "challenge_to_chess": handle_challenge_to_chess,
    "challenge_game": handle_challenge_game,
    "accept_game": handle_accept_game,
    "decline_game": handle_decline_game,
    "cancel_game": handle_cancel_game,
    "game_move": handle_game_move,
    "resign_game": handle_resign_game,
    "watch_game": handle_watch_game,
    "unwatch_game": handle_unwatch_game,
    "create_game_link": handle_create_game_link,
    "claim_game_link": handle_claim_game_link,
    "start_party_game": handle_start_party_game,
    "join_party_game": handle_join_party_game,
    "leave_party_game": handle_leave_party_game,
    "begin_party_game": handle_begin_party_game,
    "party_action": handle_party_action,
    "skip_party_round": handle_skip_party_round,
    "cancel_party_game": handle_cancel_party_game,
    "start_card_game": handle_start_card_game,
    "join_card_game": handle_join_card_game,
    "leave_card_game": handle_leave_card_game,
    "begin_card_game": handle_begin_card_game,
    "card_action": handle_card_action,
    "start_next_hand": handle_start_next_hand,
    "cancel_card_game": handle_cancel_card_game,
}


async def dispatch(session, settings, redis, hub, room, actor: Member, msg_type: str, data: dict):
    handler = HANDLERS.get(msg_type)
    if handler is None:
        raise DomainError("bad_request", f"Unknown message type '{msg_type}'.")
    await handler(session, settings, redis, hub, room, actor, data)
