from conftest import auth


def add(client, user_id, distance, seconds, day="2026-10-01"):
    body = {"distance": distance, "duration_seconds": seconds, "performed_on": day}
    return client.post("/records", json=body, headers=auth(user_id))


def test_create_and_list_records(client):
    response = add(client, 1, "10k", 2900)
    assert response.status_code == 201
    assert response.json()["distance"] == "10k"
    add(client, 1, "5k", 1300, day="2026-10-05")
    distances = [r["distance"] for r in client.get("/records", headers=auth(1)).json()]
    assert distances == ["5k", "10k"]


def test_best_record_per_distance(client):
    add(client, 1, "10k", 2900)
    add(client, 1, "10k", 2750, day="2026-10-10")
    add(client, 1, "10k", 3100)
    add(client, 1, "semi", 6000)
    add(client, 2, "10k", 2000)

    best = {r["distance"]: r["duration_seconds"] for r in client.get("/records/best", headers=auth(1)).json()}
    assert best == {"10k": 2750, "semi": 6000}


def test_rejects_unknown_distance_and_bad_duration(client):
    assert add(client, 1, "42k", 10000).status_code == 422
    assert add(client, 1, "5k", 0).status_code == 422


def test_delete_record_only_by_owner(client):
    record_id = add(client, 1, "5k", 1300).json()["id"]
    assert client.delete(f"/records/{record_id}", headers=auth(2)).status_code == 404
    assert client.delete(f"/records/{record_id}", headers=auth(1)).status_code == 204
    assert client.get("/records", headers=auth(1)).json() == []
