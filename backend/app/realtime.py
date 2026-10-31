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
from app import rooms as rooms_mod
from app.errors import DomainError
from app.models import Channel, Member, Message, new_id


async def _close_quietly(ws):
    try:
        await ws.close()
    except Exception:
        pass


class Hub:
    CHANNEL = "openhouse:events"

    def __init__(self, redis):
        self.redis = redis
        self.local: dict[str, dict[str, object]] = {}
        self.pending_offers: dict[str, str] = {}
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

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


async def _broadcast_game_state(redis, hub, room, game, state: dict) -> None:
    """Players always get it directly; watchers get it too, looked up
    fresh each time rather than kept in the event - a watcher list can
    change between moves."""
    await hub.publish(room.id, state, to_member_id=game.white_member_id)
    await hub.publish(room.id, state, to_member_id=game.black_member_id)
    for watcher_id in await watchers_snapshot(redis, game.id):
        if watcher_id in (game.white_member_id, game.black_member_id):
            continue
        await hub.publish(room.id, state, to_member_id=watcher_id)


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


async def handle_start_music(session, settings, redis, hub, room, actor, data):
    if actor.role not in ("owner", "mod"):
        raise DomainError("not_allowed", "Only the owner or a moderator can play music.")

    library_track_id = data.get("library_track_id")
    file_id = data.get("file_id")

    if library_track_id:
        track = music_library.get_track(library_track_id)
        if track is None:
            raise DomainError("bad_request", "Unknown library track.")
        state = {
            "source": "library",
            "url": track["url"],
            "filename": track["title"],
            "attribution": f'{track["artist"]} · {track["license"]}',
        }
    elif file_id:
        asset = await files_mod.get_file_or_404(session, room.id, file_id)
        if files_mod.file_extension(asset.filename) not in settings.MUSIC_EXTENSIONS:
            raise DomainError("file_type", "That file isn't a playable audio file.")
        state = {"source": "upload", "file_id": asset.id, "filename": asset.filename}
    else:
        raise DomainError("bad_request", "No file specified.")

    # Overwrites unconditionally - starting new music while something is
    # already playing just replaces it, no special-case needed. Every
    # connected client reloads on the fresh broadcast below.
    state["started_by_member_id"] = actor.id
    state["started_by_name"] = actor.display_name
    state["started_at_ms"] = int(time.time() * 1000)

    await redis.set(_music_key(room.id), json.dumps(state), ex=settings.ROOM_MUSIC_TTL_SECONDS)
    await hub.publish(room.id, {"type": "music_started", **state})


async def handle_stop_music(session, settings, redis, hub, room, actor, data):
    if actor.role not in ("owner", "mod"):
        raise DomainError("not_allowed", "Only the owner or a moderator can stop the music.")
    await redis.delete(_music_key(room.id))
    await hub.publish(room.id, {"type": "music_stopped"})


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

async def handle_challenge_to_chess(session, settings, redis, hub, room, actor, data):
    opponent = await _get_target_member(session, room.id, data.get("opponent_id"))
    game = await games_mod.create_challenge(session, room, actor, opponent)
    invite = games_mod.invite_event(game, actor, opponent)
    # Sent to both - the challenger needs the same event to learn the new
    # game_id and show a "waiting for a reply" state, same pattern as
    # handle_start_call echoing call_invite back to its own host.
    await hub.publish(room.id, invite, to_member_id=opponent.id)
    await hub.publish(room.id, invite, to_member_id=actor.id)


async def handle_accept_game(session, settings, redis, hub, room, actor, data):
    game = await games_mod.get_game_or_404(session, room.id, data.get("game_id"))
    game = await games_mod.accept_challenge(session, game, actor)
    state = await games_mod.build_state_event(session, game)
    await _broadcast_game_state(redis, hub, room, game, state)
    # Room-wide (no to_member_id) - everyone else gets a lightweight
    # "live now" banner they can tap to spectate, without being dropped
    # into the board themselves.
    white = await session.get(Member, game.white_member_id)
    black = await session.get(Member, game.black_member_id)
    await hub.publish(room.id, games_mod.live_event(game, white, black))
    await post_system_message(
        session, settings, hub, room, f"♟️ {state['white_name']} and {state['black_name']} started a game of chess!"
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
    await hub.publish(room.id, {"type": "game_cancelled", "game_id": game.id}, to_member_id=black_id)


async def handle_game_move(session, settings, redis, hub, room, actor, data):
    game = await games_mod.get_game_or_404(session, room.id, data.get("game_id"))
    from_sq, to_sq, promotion = data.get("from"), data.get("to"), data.get("promotion")
    if not from_sq or not to_sq:
        raise DomainError("bad_request", "Missing from/to.")
    uci = f"{from_sq}{to_sq}{promotion or ''}"
    game = await games_mod.apply_move(session, game, actor, uci)
    state = await games_mod.build_state_event(session, game)
    await _broadcast_game_state(redis, hub, room, game, state)
    if state["game_over"]:
        await hub.publish(room.id, {"type": "game_live_ended", "game_id": game.id})
        await post_system_message(session, settings, hub, room, _result_message(state))


async def handle_resign_game(session, settings, redis, hub, room, actor, data):
    game = await games_mod.get_game_or_404(session, room.id, data.get("game_id"))
    game = await games_mod.resign(session, game, actor)
    state = await games_mod.build_state_event(session, game)
    await _broadcast_game_state(redis, hub, room, game, state)
    await hub.publish(room.id, {"type": "game_live_ended", "game_id": game.id})
    await post_system_message(session, settings, hub, room, _result_message(state))


async def handle_watch_game(session, settings, redis, hub, room, actor, data):
    game = await games_mod.get_game_or_404(session, room.id, data.get("game_id"))
    await _watch_game(redis, hub, settings, room.id, game.id, actor.id)
    # The watcher needs the current board immediately, not just future
    # moves - a direct send, same reasoning as the connect-time snapshot.
    state = await games_mod.build_state_event(session, game)
    await hub.publish(room.id, state, to_member_id=actor.id)


async def handle_unwatch_game(session, settings, redis, hub, room, actor, data):
    game_id = data.get("game_id")
    if not game_id:
        raise DomainError("bad_request", "Missing game_id.")
    await _unwatch_game(redis, hub, room.id, game_id, actor.id)


def _result_message(state: dict) -> str:
    white, black = state["white_name"], state["black_name"]
    if state["result"] == "draw":
        return f"♟️ {white} and {black}'s chess game ended in a draw ({state['termination'].replace('_', ' ')})."
    winner = white if state["result"] == "white" else black
    loser = black if state["result"] == "white" else white
    if state["termination"] == "resignation":
        return f"♟️ {winner} wins! {loser} resigned."
    if state["termination"] == "checkmate":
        return f"♟️ Checkmate! {winner} wins the chess game."
    return f"♟️ {winner} wins the chess game ({state['termination'].replace('_', ' ')})."


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
    "start_call": handle_start_call,
    "join_call": handle_join_call,
    "leave_call": handle_leave_call,
    "call_offer": handle_call_offer,
    "call_answer": handle_call_answer,
    "call_ice_candidate": handle_call_ice_candidate,
    "challenge_to_chess": handle_challenge_to_chess,
    "accept_game": handle_accept_game,
    "decline_game": handle_decline_game,
    "cancel_game": handle_cancel_game,
    "game_move": handle_game_move,
    "resign_game": handle_resign_game,
    "watch_game": handle_watch_game,
    "unwatch_game": handle_unwatch_game,
}


async def dispatch(session, settings, redis, hub, room, actor: Member, msg_type: str, data: dict):
    handler = HANDLERS.get(msg_type)
    if handler is None:
        raise DomainError("bad_request", f"Unknown message type '{msg_type}'.")
    await handler(session, settings, redis, hub, room, actor, data)
