def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def create_room(client, name="Test Room", owner_name="Owner"):
    resp = await client.post("/api/rooms", json={"name": name, "owner_name": owner_name})
    assert resp.status_code == 200, resp.text
    return resp.json()


# No METERED_API_KEY configured (the test Settings default) - falls back
# to STUN-only rather than erroring, same as local dev without a real
# Metered account. The real-Metered-API success path isn't covered here
# on purpose - no outbound network calls in tests.

async def test_requires_a_valid_session(client):
    resp = await client.get("/api/turn-credentials", headers=auth("not-a-real-token"))
    assert resp.status_code == 401
    assert resp.json()["code"] == "bad_token"


async def test_rejects_missing_token(client):
    resp = await client.get("/api/turn-credentials")
    assert resp.status_code == 401


async def test_falls_back_to_stun_only_when_metered_not_configured(client):
    data = await create_room(client)
    resp = await client.get("/api/turn-credentials", headers=auth(data["session_token"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["iceServers"] == [{"urls": "stun:stun.l.google.com:19302"}]
