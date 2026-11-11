from conftest import auth

SESSION = {
    "performed_on": "2026-11-10",
    "notes": "  Bonne séance  ",
    "sets": [
        {"exercise": " Squat ", "reps": 8, "weight_kg": 100},
        {"exercise": "Squat", "reps": 6, "weight_kg": 110},
        {"exercise": "Développé couché", "reps": 10, "weight_kg": 70.5},
    ],
}


def test_create_and_read_session(client):
    response = client.post("/sessions", json=SESSION, headers=auth(1))
    assert response.status_code == 201
    body = response.json()
    assert body["notes"] == "Bonne séance"
    assert [s["exercise"] for s in body["sets"]] == ["Squat", "Squat", "Développé couché"]

    read = client.get(f"/sessions/{body['id']}", headers=auth(1))
    assert read.json() == body


def test_list_sessions_newest_first(client):
    client.post("/sessions", json=SESSION, headers=auth(1))
    client.post("/sessions", json={**SESSION, "performed_on": "2026-11-11"}, headers=auth(1))
    dates = [s["performed_on"] for s in client.get("/sessions", headers=auth(1)).json()]
    assert dates == ["2026-11-11", "2026-11-10"]


def test_users_cannot_see_or_delete_each_other_sessions(client):
    session_id = client.post("/sessions", json=SESSION, headers=auth(1)).json()["id"]
    assert client.get("/sessions", headers=auth(2)).json() == []
    assert client.get(f"/sessions/{session_id}", headers=auth(2)).status_code == 404
    assert client.delete(f"/sessions/{session_id}", headers=auth(2)).status_code == 404
    assert client.get(f"/sessions/{session_id}", headers=auth(1)).status_code == 200


def test_delete_session(client):
    session_id = client.post("/sessions", json=SESSION, headers=auth(1)).json()["id"]
    assert client.delete(f"/sessions/{session_id}", headers=auth(1)).status_code == 204
    assert client.get(f"/sessions/{session_id}", headers=auth(1)).status_code == 404
    assert client.get("/exercises", headers=auth(1)).json() == []


def test_rejects_invalid_sessions(client):
    invalid = [
        {**SESSION, "sets": []},
        {**SESSION, "sets": [{"exercise": "Squat", "reps": 0, "weight_kg": 100}]},
        {**SESSION, "sets": [{"exercise": "Squat", "reps": 5, "weight_kg": -1}]},
        {**SESSION, "sets": [{"exercise": "   ", "reps": 5, "weight_kg": 10}]},
        {**SESSION, "performed_on": "pas-une-date"},
    ]
    for body in invalid:
        assert client.post("/sessions", json=body, headers=auth(1)).status_code == 422


def test_exercise_stats(client):
    client.post("/sessions", json=SESSION, headers=auth(1))
    client.post(
        "/sessions",
        json={
            "performed_on": "2026-11-12",
            "sets": [{"exercise": "squat", "reps": 3, "weight_kg": 105}],
        },
        headers=auth(1),
    )
    client.post("/sessions", json=SESSION, headers=auth(2))

    stats = client.get("/exercises", headers=auth(1)).json()
    assert stats == [
        {
            "exercise": "Développé couché",
            "best_weight_kg": 70.5,
            "total_sets": 1,
            "last_performed_on": "2026-11-10",
        },
        {
            "exercise": "squat",
            "best_weight_kg": 110,
            "total_sets": 3,
            "last_performed_on": "2026-11-12",
        },
    ]
