"""Reproducible jury upload using the real catalog and explicit test profiles."""

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "jury"


def recommend(client, employee_id):
    response = client.post("/api/recommend", json={"employee_id": employee_id})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["llm_used"] is False
    assert len(result["recommendations"]) + len(result["not_recommended"]) == 40
    return result


def test_jury_upload_history_trap_progress_hr_and_reset(client):
    baseline = client.app.state.store.snapshot()
    baseline_participation = client.get("/api/hr/overview").json()["activity_participation"]
    baseline_club = next(item for item in baseline_participation if item["event_id"] == "EV_036")
    files = [("files[]", (name, (FIXTURES / name).read_bytes()))
             for name in ("employees.json", "activity_history.csv")]
    uploaded = client.post("/api/upload", files=files)
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["loaded"] == {
        "employees": 3, "history_rows": 3, "events": 0, "skills": 0, "role_profiles": 0,
    }
    assert client.get("/api/health").json()["employees_loaded"] == 203
    state = client.app.state.store.snapshot()
    assert state.events == baseline.events
    assert state.roles == baseline.roles
    assert state.employees["JURY_HISTORY_TRAP"].skills == state.employees["JURY_NO_HISTORY"].skills

    trap = recommend(client, "JURY_HISTORY_TRAP")
    assert [item["event_id"] for item in trap["recommendations"]] == ["EV_006", "EV_007"]
    for item in trap["recommendations"]:
        assert item["factors"]["grade_criticality"] == "critical_for_Senior"
        assert item["factors"]["gap_closure"]["skill"] == "SK_SYSTEM_DESIGN"
        assert item["explanation"]
    rejected_club = next(item for item in trap["not_recommended"] if item["event_id"] == "EV_036")
    assert rejected_club["reason_code"] == "history_penalty"
    assert rejected_club["factors"]["history_fit"]["similar_skipped"] == 3
    assert rejected_club["factors"]["gap_closure"] == {
        "skill": "SK_PUBLIC_SPEAKING", "current": 0, "required": 2, "gain": 1,
    }
    assert rejected_club["factors"]["score_breakdown"] == {
        "gap": 20, "achievability": 10, "criticality": 0, "history_penalty": 90, "total": -60,
    }
    # Even the obvious low-skill course must obey its actual ceiling.
    capped = next(item for item in trap["not_recommended"] if item["event_id"] == "EV_005")
    assert capped["reason_code"] == "ineligible" and capped["factors"] is None

    control = recommend(client, "JURY_NO_HISTORY")
    assert [item["event_id"] for item in control["recommendations"]] == ["EV_006", "EV_007", "EV_036"]
    assert control["recommendations"][2]["factors"]["score_breakdown"]["total"] == 30
    assert recommend(client, "JURY_REQUIREMENTS_MET")["recommendations"] == []

    # A repeated jury upload is a merge, not duplicated history or a replacement dataset.
    assert client.post("/api/upload", files=files).status_code == 200
    assert len(client.app.state.store.snapshot().history) == len(baseline.history) + 3
    assert recommend(client, "JURY_HISTORY_TRAP")["recommendations"] == trap["recommendations"]
    hr = client.get("/api/hr/overview").json()
    assert hr["totals"]["employees"] == 203
    assert "JURY_REQUIREMENTS_MET" in {item["employee_id"] for item in hr["no_recommendation"]}
    assert "JURY_HISTORY_TRAP" not in {item["employee_id"] for item in hr["no_recommendation"]}
    club = next(item for item in hr["activity_participation"] if item["event_id"] == "EV_036")
    assert club["skipped"] == baseline_club["skipped"] + 3

    profile = client.get("/api/employees/JURY_HISTORY_TRAP").json()
    completed = client.post("/api/complete", json={"employee_id": "JURY_HISTORY_TRAP", "event_id": "EV_006"})
    assert completed.status_code == 200, completed.text
    result = completed.json()
    system_design = next(item for item in result["updated_skills"] if item["code"] == "SK_SYSTEM_DESIGN")
    assert (system_design["before"], system_design["after"]) == (3, 4)
    assert result["trajectory"]["attained_level_sum"] == profile["trajectory"]["attained_level_sum"] + 1
    assert result["trajectory"]["required_level_sum"] == profile["trajectory"]["required_level_sum"]
    assert result["trajectory"]["progress_to_next_grade"] > profile["trajectory"]["progress_to_next_grade"]
    assert result["new_recommendations"] == []
    assert client.get("/api/employees/JURY_HISTORY_TRAP").json()["grade"] == "Middle"
    hr = client.get("/api/hr/overview").json()
    no_step = next(item for item in hr["no_recommendation"] if item["employee_id"] == "JURY_HISTORY_TRAP")
    assert "штраф за историю" in no_step["reason"]

    assert client.post("/api/reset").status_code == 200
    restored = client.app.state.store.snapshot()
    assert restored.employees == baseline.employees
    assert restored.history == baseline.history
    assert client.get("/api/employees/JURY_HISTORY_TRAP").status_code == 404
