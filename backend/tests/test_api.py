import pytest


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_auth_flow(client):
    r = await client.post("/api/auth/register", json={"email": "test@example.com", "password": "secret"})
    assert r.status_code == 200
    user = r.json()
    assert user["email"] == "test@example.com"

    r = await client.post("/api/auth/token", data={"username": "test@example.com", "password": "secret"})
    assert r.status_code == 200
    token = r.json()["access_token"]

    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "test@example.com"
