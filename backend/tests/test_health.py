async def test_healthz_returns_200_with_no_external_dependencies(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
