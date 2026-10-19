async def create_room(client, name="Test Room", owner_name="Owner"):
    resp = await client.post("/api/rooms", json={"name": name, "owner_name": owner_name})
    assert resp.status_code == 200, resp.text
    return resp.json()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def admin_headers(app):
    return {"X-Admin-Token": app.state.settings.ADMIN_TOKEN}


async def join(client, code, name):
    resp = await client.post(f"/api/rooms/{code}/join", json={"name": name, "over_18": True})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_report_reaches_admin_queue(client, app):
    data = await create_room(client)
    room_id, code = data["room"]["id"], data["room"]["code"]
    reporter = await join(client, code, "Reporter")

    resp = await client.post(
        f"/api/rooms/{room_id}/reports",
        json={"reason": "spamming links", "target_member_id": data["member"]["member_id"]},
        headers=auth(reporter["session_token"]),
    )
    assert resp.status_code == 200
    report_id = resp.json()["report_id"]

    denied = await client.get("/api/admin/reports")
    assert denied.status_code == 403
    assert denied.json()["code"] == "not_allowed"

    listed = await client.get("/api/admin/reports", headers=admin_headers(app))
    assert listed.status_code == 200
    reports = listed.json()["reports"]
    assert any(r["id"] == report_id and r["status"] == "open" for r in reports)

    resolved = await client.post(f"/api/admin/reports/{report_id}/resolve", headers=admin_headers(app))
    assert resolved.status_code == 200

    listed2 = await client.get("/api/admin/reports", headers=admin_headers(app))
    assert next(r for r in listed2.json()["reports"] if r["id"] == report_id)["status"] == "done"


async def test_admin_metrics_count_rooms_and_joins(client, app):
    await create_room(client)
    metrics_resp = await client.get("/api/admin/metrics", headers=admin_headers(app))
    assert metrics_resp.status_code == 200
    rows = metrics_resp.json()["metrics"]
    rooms_created = next((r for r in rows if r["name"] == "rooms_created"), None)
    assert rooms_created is not None
    assert rooms_created["value"] >= 1
