import json

TRACKING = "http://tracking-service:8000"
SESSION = {
    "id": 7,
    "performed_on": "2026-11-10",
    "notes": "Jambes",
    "sets": [
        {"id": 1, "exercise": "Squat", "reps": 8, "weight_kg": 100.0},
        {"id": 2, "exercise": "Squat", "reps": 6, "weight_kg": 107.5},
    ],
}


def test_dashboard(logged_client, services):
    services.on("GET", f"{TRACKING}/sessions", json=[SESSION])
    services.on("GET", f"{TRACKING}/records/best", json=[
        {"id": 2, "distance": "semi", "duration_seconds": 6123, "performed_on": "2026-09-01"},
        {"id": 1, "distance": "5k", "duration_seconds": 1290, "performed_on": "2026-10-01"},
    ])
    services.on("GET", f"{TRACKING}/exercises", json=[
        {"exercise": "Squat", "best_weight_kg": 107.5, "total_sets": 2, "last_performed_on": "2026-11-10"},
    ])
    page = logged_client.get("/dashboard").text
    assert "107.5 kg" in page
    assert "1:42:03" in page and "21:30" in page
    assert page.index("5 km") < page.index("Semi-marathon")


def test_create_session_sends_only_filled_rows(logged_client, services):
    services.on("POST", f"{TRACKING}/sessions", 201, SESSION)
    form = {
        "performed_on": "2026-11-10",
        "notes": "Jambes",
        "exercise": ["Squat", "", "Squat"],
        "reps": ["8", "", "6"],
        "weight_kg": ["100", "", "107,5"],
    }
    response = logged_client.post("/sessions/new", data=form)
    assert response.headers["location"] == "/sessions/7"
    sent = json.loads(services.last("POST", f"{TRACKING}/sessions").content)
    assert sent["sets"] == [
        {"exercise": "Squat", "reps": 8, "weight_kg": 100.0},
        {"exercise": "Squat", "reps": 6, "weight_kg": 107.5},
    ]


def test_create_session_keeps_input_on_error(logged_client, services):
    form = {"performed_on": "2026-11-10", "exercise": ["Squat"], "reps": ["huit"], "weight_kg": ["100"]}
    response = logged_client.post("/sessions/new", data=form)
    assert response.status_code == 400
    assert 'value="huit"' in response.text
    assert services.requests == []

    empty = {"performed_on": "2026-11-10", "exercise": [""], "reps": [""], "weight_kg": [""]}
    assert "Ajoute au moins une série" in logged_client.post("/sessions/new", data=empty).text


def test_session_detail_and_delete(logged_client, services):
    services.on("GET", f"{TRACKING}/sessions/7", json=SESSION)
    assert "Séance du 2026-11-10" in logged_client.get("/sessions/7").text

    services.on("GET", f"{TRACKING}/sessions/8", 404, {"detail": "Introuvable"})
    assert logged_client.get("/sessions/8").status_code == 404

    services.on("DELETE", f"{TRACKING}/sessions/7", 204)
    assert logged_client.post("/sessions/7/delete").headers["location"] == "/sessions"


def test_add_record_converts_time(logged_client, services):
    services.on("POST", f"{TRACKING}/records", 201, {"id": 1})
    form = {"distance": "10k", "hours": "", "minutes": "45", "seconds": "30", "performed_on": "2026-11-01"}
    assert logged_client.post("/records", data=form).headers["location"] == "/records"
    sent = json.loads(services.last("POST", f"{TRACKING}/records").content)
    assert sent == {"distance": "10k", "duration_seconds": 2730, "performed_on": "2026-11-01"}


def test_records_page_marks_best(logged_client, services):
    records = [
        {"id": 1, "distance": "10k", "duration_seconds": 2730, "performed_on": "2026-11-01"},
        {"id": 2, "distance": "10k", "duration_seconds": 2900, "performed_on": "2026-10-01"},
    ]
    services.on("GET", f"{TRACKING}/records", json=records)
    services.on("GET", f"{TRACKING}/records/best", json=records[:1])
    page = logged_client.get("/records").text
    assert page.count('class="badge">Record') == 1
