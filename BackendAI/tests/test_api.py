import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException

from app.services.completion import complete
from app.services.scoring import rank


def upload(client, filename, payload, field="files"):
    content = json.dumps(payload).encode() if not isinstance(payload, bytes) else payload
    return client.post("/api/upload", files=[(field, (filename, content))])


def test_static_files_are_independent_of_cwd(config, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app

    monkeypatch.chdir(tmp_path)
    with TestClient(create_app(config)) as client:
        index = client.get("/")
        assert index.status_code == 200
        assert index.headers["content-type"].startswith("text/html")
        assert "Career Quest" in index.text
        script = client.get("/static/app.js")
        assert script.status_code == 200
        assert "async function api" in script.text


def test_real_dataset_and_profile_contract(client):
    health = client.get("/api/health").json()
    assert health == {"status": "ok", "llm_available": False, "employees_loaded": 200,
                      "snapshot_date": "2026-10-01"}
    assert client.get("/api/v1/health").json() == health
    assert len(client.get("/api/employees").json()) == 50
    assert len(client.get("/api/employees?limit=1000").json()) == 200
    assert client.get("/api/employees?search=marat%20yessenov").json()[0]["employee_id"] == "E0001"
    assert client.get("/api/employees?search=E0001&grade=Lead").json() == []
    employees = client.get("/api/employees?role=Backend%20Engineer&grade=Junior").json()
    assert employees and all(row["role"] == "Backend Engineer" and row["grade"] == "Junior" for row in employees)
    profile = client.get("/api/employees/E0001").json()
    assert profile["next_grade"] == "Middle"
    assert profile["tenure_months"] == 5
    assert 0 <= profile["trajectory"]["progress_to_next_grade"] <= 1
    assert all(skill["gap"] == max(0, (skill["required_next"] or 0) - skill["current"]) for skill in profile["skills"])
    schema = client.get("/api/v1/openapi.json")
    assert schema.status_code == 200
    assert "/api/upload" in schema.json()["paths"]


def test_recommend_complete_reset_flow(client):
    request = {"employee_id": "E0001"}
    baseline = client.get("/api/employees/E0001").json()
    before = client.post("/api/recommend", json=request).json()
    again = client.post("/api/recommend/E0001").json()
    assert before["recommendations"] == again["recommendations"]
    assert before["llm_used"] is False
    assert 1 <= len(before["recommendations"]) <= 3
    assert all(item["explanation"] and item["explanation_source"] == "template" for item in before["recommendations"])
    event = before["recommendations"][0]["event_id"]
    result = client.post("/api/complete", json={**request, "event_id": event})
    assert result.status_code == 200, result.text
    result = result.json()
    assert any(item["after"] > item["before"] for item in result["updated_skills"])
    assert result["trajectory"]["progress_to_next_grade"] > baseline["trajectory"]["progress_to_next_grade"]
    assert result["trajectory"]["previous_progress_to_next_grade"] == baseline["trajectory"]["progress_to_next_grade"]
    assert event not in {item["event_id"] for item in result["new_recommendations"]}
    after = client.get("/api/employees/E0001").json()
    assert client.post(f"/api/complete/E0001/{event}").status_code == 409
    assert client.get("/api/employees/E0001").json() == after
    assert client.post("/api/reset").status_code == 200
    assert client.get("/api/employees/E0001").json() == baseline


def test_completion_is_atomic_under_concurrent_requests(store):
    data = store.snapshot()
    event = rank(data, data.employees["E0001"])[0][0].event_id

    def finish():
        try:
            complete(store, "E0001", event)
            return 200
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: finish(), range(2))) == [200, 409]


def test_employee_upload_merges_and_reset_restores(client):
    data = client.app.state.store.snapshot()
    employee = data.employees["E0001"].model_dump(mode="json")
    employee.update(employee_id="JURY_NEW", full_name="Jury Employee")
    result = upload(client, "employees.json", {"employees": [employee]}, field="files[]")
    assert result.status_code == 200, result.text
    assert result.json()["loaded"]["employees"] == 1
    assert result.json()["employee_ids"] == ["JURY_NEW"]
    assert client.get("/api/health").json()["employees_loaded"] == 201
    assert client.post("/api/recommend", json={"employee_id": "JURY_NEW"}).status_code == 200
    employee["full_name"] = "Updated Jury"
    assert upload(client, "employees.json", [employee]).json()["warnings"]
    assert client.get("/api/employees/JURY_NEW").json()["name"] == "Updated Jury"
    assert client.get("/api/health").json()["employees_loaded"] == 201
    client.post("/api/reset")
    assert client.get("/api/employees/JURY_NEW").status_code == 404


def test_upload_all_files_resolves_cross_references_atomically(client):
    data = client.app.state.store.snapshot()
    employee = data.employees["E0001"].model_dump(mode="json")
    employee.update(employee_id="JURY_NEW", skills={"JURY_SKILL": 1}, last_review_date="2026-01-01")
    event = data.events["EV_005"].model_dump(mode="json")
    event.update(event_id="JURY_EVENT", develops_skills=[{"skill_id": "JURY_SKILL", "gain": 2, "max_level": 4}],
                 prerequisites={}, target_roles=[], target_grades=[])
    skill = {"skill_id": "JURY_SKILL", "name": "Uploaded Skill", "type": "hard"}
    history = ("record_id,employee_id,event_id,date,status,completion_pct\n"
               "JURY_RECORD,JURY_NEW,JURY_EVENT,2026-09-01,completed,100\n")
    # Deliberately submit references before the files defining them.
    files = [("files", ("activity_history.csv", history)),
             ("files", ("employees.json", json.dumps([employee]))),
             ("files", ("events.json", json.dumps([event]))),
             ("files", ("skills.json", json.dumps({"skills": [skill]})))]
    response = client.post("/api/upload", files=files)
    assert response.status_code == 200, response.text
    assert response.json()["loaded"] == {"employees": 1, "events": 1, "skills": 1, "role_profiles": 0, "history_rows": 1}
    state = client.app.state.store.snapshot()
    assert state.effective_skills["JURY_NEW"]["JURY_SKILL"] == 3
    assert len(state.employees) == 201 and len(state.events) == 41
    assert client.post("/api/upload", files=files).status_code == 200
    assert client.app.state.store.snapshot().effective_skills["JURY_NEW"]["JURY_SKILL"] == 3


def test_upload_invalid_batch_preserves_state(client):
    original = client.app.state.store.snapshot()
    employee = original.employees["E0001"].model_dump(mode="json")
    employee["full_name"] = "Should not persist"
    invalid_event = original.events["EV_005"].model_dump(mode="json")
    invalid_event["prerequisites"] = {"UNKNOWN_SKILL": 2}
    response = client.post("/api/upload", files=[
        ("files", ("employees.json", json.dumps([employee]))),
        ("files", ("events.json", json.dumps([invalid_event]))),
    ])
    assert response.status_code == 422
    assert response.json()["error_code"] == "INVALID_DATASET"
    assert client.app.state.store.snapshot() is original


@pytest.mark.parametrize("filename,content", [
    ("employees.json", b"{"), ("employees.json", b"\xff"), ("employees.json", b"{}"),
    ("employees.json", b'[{"employee_id":""}]'),
    ("activity_history.csv", b"employee_id,event_id\nE0001,EV_001"),
    ("activity_history.csv", b"record_id,employee_id,event_id,date,status,completion_pct\nR,E0001,EV_001,bad,completed,100"),
    ("skills.json", b'{"skills":[{"skill_id":"X","name":"X","type":"unknown"}]}'),
    ("../employees.json", b"[]"),
])
def test_invalid_uploads_return_json(client, filename, content):
    result = upload(client, filename, content)
    assert result.status_code == 422
    assert result.json()["success"] is False


def test_upload_duplicates_empty_and_size_limit(client):
    assert client.post("/api/upload").status_code == 422
    assert client.post("/api/upload", files=[("files", ("employees.json", "[]"))] * 2).status_code == 422
    client.app.state.settings.MAX_UPLOAD_BYTES = 5
    assert upload(client, "employees.json", b"[      ]").status_code == 413


def test_validation_not_found_and_global_errors(client, monkeypatch):
    for endpoint, payload in [("/api/recommend", {}), ("/api/complete", {"employee_id": " "})]:
        response = client.post(endpoint, json=payload)
        assert response.status_code == 422 and response.json()["error_code"] == "VALIDATION_ERROR"
    assert client.get("/api/employees?limit=0").status_code == 422
    assert client.post("/api/recommend", json={"employee_id": "missing"}).status_code == 404
    assert client.post("/api/complete", json={"employee_id": "E0001", "event_id": "missing"}).status_code == 404
    assert client.get("/missing").json()["error_code"] == "HTTP_404"

    def fail():
        raise RuntimeError("sensitive debug details")

    monkeypatch.setattr(client.app.state.store, "snapshot", fail)
    response = client.get("/api/health")
    assert response.status_code == 500
    assert "sensitive" not in response.text


def test_hr_overview_uses_dataset_counts(client):
    result = client.get("/api/hr/overview")
    assert result.status_code == 200
    result = result.json()
    assert result["totals"]["employees"] == 200
    assert 0 <= result["totals"]["with_gaps"] <= 200
    data = client.app.state.store.snapshot()
    assert sum(row["attended"] for row in result["activity_participation"]) == sum(
        row.status == "completed" for row in data.history.values())
    assert len(result["activity_participation"]) == 40
    assert all(0 <= row["rate"] <= 1 for row in result["activity_participation"])
    assert all(row["reason"] for row in result["no_recommendation"])
