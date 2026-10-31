"""Shared domain error type.

Business logic in rooms.py/members.py/messages.py/safety.py/files.py
raises DomainError with one of SPEC.md's error codes. The REST layer
in main.py turns it into an HTTP response; the WebSocket layer in
realtime.py turns it into an `error` event. The logic itself doesn't
know or care which transport is calling it.
"""

HTTP_STATUS_BY_CODE = {
    "bad_code": 404,
    "bad_invite": 400,
    "pending_approval": 202,
    "banned": 403,
    "not_allowed": 403,
    "rate_limited": 429,
    "file_too_large": 413,
    "file_type": 415,
    "room_ended": 410,
    "bad_request": 400,
    "bad_token": 401,
    "wrong_network": 403,
    "game_in_progress": 409,
    "not_your_turn": 403,
    "illegal_move": 400,
}


class DomainError(Exception):
    def __init__(self, code: str, message: str | None = None):
        self.code = code
        self.message = message or code
        super().__init__(self.message)

    @property
    def http_status(self) -> int:
        return HTTP_STATUS_BY_CODE.get(self.code, 400)
