from datetime import date

import pytest
from fastapi import HTTPException

from app.schemas import Employee, Event, HistoryRecord, RoleProfile, Skill
from app.services.completion import complete
from app.services.loader import Dataset
from app.services.profiles import profile
from app.services.scoring import eligibility_reason, rank


def scenario(*, history=(), events=None, skills=None, review=date(2026, 9, 1), grade="Middle"):
    """Small controlled data for boundary cases; API tests use the supplied dataset."""
    employee = Employee(
        employee_id="TEST", full_name="Test Employee", role="Engineer", grade=grade,
        skills={"DESIGN": 2, "SPEAK": 0} if skills is None else skills, last_review_date=review,
    )
    catalog = events or [event("DESIGN_COURSE", "DESIGN"), event("SPEAK_COURSE", "SPEAK", type="workshop")]
    target = RoleProfile(role="Engineer", grade="Senior", required_skills={"DESIGN": 4, "SPEAK": 1},
                         critical_skills=["DESIGN"])
    return Dataset(
        employees={"TEST": employee}, events={item.event_id: item for item in catalog},
        skills={code: Skill(skill_id=code, name=code, type="hard") for code in ("DESIGN", "SPEAK")},
        roles={(employee.role, employee.grade): RoleProfile(role=employee.role, grade=employee.grade, required_skills={}),
               (target.role, target.grade): target}, history={item.record_id: item for item in history},
        snapshot_date=date(2026, 10, 1),
    )


def event(identifier, skill="DESIGN", **kwargs):
    values = dict(event_id=identifier, title=identifier, type="course", format="self_paced", duration_hours=4,
                  mandatory=False, develops_skills=[{"skill_id": skill, "gain": 1, "max_level": 5}])
    return Event(**(values | kwargs))


def history(identifier, event_id, status, when="2026-09-15"):
    return HistoryRecord(record_id=identifier, employee_id="TEST", event_id=event_id, date=when, status=status,
                         completion_pct=100 if status == "completed" else 30 if status in ("dropped", "in_progress") else 0)


def test_every_real_employee_has_deterministic_eligible_recommendations(store):
    data = store.snapshot()
    for employee in data.employees.values():
        first, excluded = rank(data, employee)
        assert first == rank(data, employee)[0]
        assert len(first) <= 3
        assert len({item.event_id for item in first}) == len(first)
        for item in first:
            assert eligibility_reason(data, employee, data.events[item.event_id]) is None
            assert 0 < item.score < 1
            assert item.factors.score_breakdown.total > 0
        assert not {item.event_id for item in first} & {item.event_id for item in excluded}
        assert len(first) + len(excluded) == len(data.events)
        assert len({item.event_id for item in excluded}) == len(excluded)
        assert excluded == rank(data, employee)[1]
        for item in excluded:
            if item.reason_code in ("history_penalty", "lower_priority"):
                assert item.factors is not None
            else:
                assert item.factors is None
            if data.events[item.event_id].mandatory:
                assert item.reason_code == "ineligible"
                assert item.factors is None


def test_critical_gap_beats_lowest_absolute_skill_and_ties_use_id():
    data = scenario(events=[event("Z", "DESIGN"), event("A", "DESIGN"), event("S", "SPEAK")])
    results, _ = rank(data, data.employees["TEST"])
    assert [item.event_id for item in results] == ["A", "Z", "S"]
    assert results[0].factors.grade_criticality == "critical_for_Senior"


def test_three_negative_attempts_avoid_speaking_trap():
    rows = [history(f"H{i}", "SPEAK_COURSE", status) for i, status in enumerate(["dropped", "no_show", "declined"])]
    data = scenario(history=rows)
    results, excluded = rank(data, data.employees["TEST"])
    assert [item.event_id for item in results] == ["DESIGN_COURSE"]
    trap = next(item for item in excluded if item.event_id == "SPEAK_COURSE")
    assert "штраф за историю" in trap.reason
    assert trap.reason_code == "history_penalty"
    assert trap.factors.history_fit.similar_skipped == 2
    assert trap.factors.history_fit.similar_declined == 1
    assert trap.factors.score_breakdown.model_dump() == {
        "gap": 10, "achievability": 10, "criticality": 0, "history_penalty": 90, "total": -70,
    }


def test_positive_candidates_outside_top_three_have_comparable_factors():
    data = scenario(events=[event("C"), event("B"), event("A"), event("S", "SPEAK")])
    selected, excluded = rank(data, data.employees["TEST"])
    assert [item.event_id for item in selected] == ["A", "B", "C"]
    alternative, = excluded
    assert alternative.event_id == "S"
    assert alternative.reason_code == "lower_priority"
    assert alternative.factors.score_breakdown.total == 20
    assert alternative.compared_with.event_id == "C"
    assert alternative.compared_with.score_breakdown.total == 50
    assert alternative.compared_with.tied is False


def test_cutoff_tie_is_explained_without_claiming_higher_score():
    data = scenario(events=[event(identifier) for identifier in ("D", "B", "C", "A")])
    selected, excluded = rank(data, data.employees["TEST"])
    assert [item.event_id for item in selected] == ["A", "B", "C"]
    alternative, = excluded
    assert alternative.event_id == "D"
    assert alternative.compared_with.tied is True
    assert alternative.factors.score_breakdown == alternative.compared_with.score_breakdown
    assert "равенстве" in alternative.reason


def test_progress_exposes_capped_numerator_and_denominator():
    data = scenario(skills={"DESIGN": 5, "SPEAK": 0})
    progress = profile(data, data.employees["TEST"]).trajectory
    assert progress.attained_level_sum == 4  # excess DESIGN cannot substitute for SPEAK
    assert progress.required_level_sum == 5
    assert progress.progress_to_next_grade == 0.8


def test_mandatory_activity_cannot_award_simulated_progress(store):
    store._state = scenario(events=[event("MANDATORY", mandatory=True)])
    before = store.snapshot()
    with pytest.raises(HTTPException) as failure:
        complete(store, "TEST", "MANDATORY")
    assert failure.value.status_code == 409
    assert store.snapshot() is before
    assert store.snapshot().effective_skills["TEST"]["DESIGN"] == 2
    assert not store.snapshot().history


def test_history_matches_type_or_skill_and_counts_once():
    events = [event("CANDIDATE"), event("SAME_SKILL", type="mentoring"), event("SAME_TYPE", "SPEAK")]
    rows = [history("H1", "SAME_SKILL", "declined"), history("H2", "SAME_TYPE", "no_show")]
    data = scenario(events=events, history=rows)
    result, excluded = rank(data, data.employees["TEST"])
    assert "CANDIDATE" in {item.event_id for item in excluded}  # base 50 minus two penalties of 30
    data = scenario(events=events, history=[history("H", "CANDIDATE", "dropped")])
    result, _ = rank(data, data.employees["TEST"])
    candidate = next(item for item in result if item.event_id == "CANDIDATE")
    assert candidate.factors.history_fit.similar_skipped == 1
    assert candidate.factors.score_breakdown.history_penalty == 30


def test_all_hard_constraints_and_repeatable_exception():
    events = [
        event("MANDATORY", mandatory=True), event("COMPLETED"), event("PENDING"),
        event("PREREQ", prerequisites={"DESIGN": 5}),
        event("CAPPED", develops_skills=[{"skill_id": "DESIGN", "gain": 1, "max_level": 2}]),
        event("WRONG_ROLE", target_roles=["Other"]), event("WRONG_GRADE", target_grades=["Lead"]),
        event("NO_SESSION", format="online", upcoming_sessions=["2026-09-30"]),
        event("EV_036"),
    ]
    data = scenario(events=events, history=[history("H1", "COMPLETED", "completed", "2026-08-01"),
                                          history("H2", "PENDING", "in_progress"),
                                          history("H3", "EV_036", "completed", "2026-08-01")])
    results, excluded = rank(data, data.employees["TEST"])
    assert [item.event_id for item in results] == ["EV_036"]
    assert len(excluded) == 8


def test_review_replay_caps_and_missing_skill_zero():
    events = [event("EARLY"), event("LATER"), event("CAPPED", develops_skills=[{"skill_id": "DESIGN", "gain": 3, "max_level": 3}]),
              event("NEW_SKILL", "SPEAK")]
    rows = [history("H1", "EARLY", "completed", "2026-08-01"),
            history("H2", "EARLY", "completed", "2026-09-01"),
            history("H3", "LATER", "completed", "2026-09-02"),
            history("H4", "CAPPED", "completed", "2026-09-03"),
            history("H5", "NEW_SKILL", "completed", "2026-09-04")]
    data = scenario(events=events, history=rows, skills={"DESIGN": 3})
    assert data.effective_skills["TEST"] == {"DESIGN": 4, "SPEAK": 1}
    assert data.completion_gains["H4"]["DESIGN"] == 0
    assert data.employees["TEST"].skills == {"DESIGN": 3}  # assessment remains unchanged


def test_future_history_does_not_affect_current_snapshot():
    data = scenario(history=[history("FUTURE", "DESIGN_COURSE", "completed", "2026-10-02")])
    assert data.effective_skills["TEST"]["DESIGN"] == 2
    assert "DESIGN_COURSE" in {item.event_id for item in rank(data, data.employees["TEST"])[0]}


def test_completion_on_review_day_and_pending_completion_order(store):
    events = [event("A", develops_skills=[{"skill_id": "DESIGN", "gain": 2, "max_level": 3}]),
              event("B", develops_skills=[{"skill_id": "DESIGN", "gain": 1, "max_level": 5}])]
    data = scenario(events=events, skills={"DESIGN": 1}, review=date(2026, 10, 1),
                    history=[history("OLD_ENROLLMENT", "B", "in_progress")])
    store._state = data
    complete(store, "TEST", "A")
    new, result = complete(store, "TEST", "B")
    assert result.updated_skills[0].before == 3
    assert result.updated_skills[0].after == 4
    assert new.effective_skills["TEST"]["DESIGN"] == 4
    assert not any(row.status == "in_progress" for row in new.history.values())
    # A later merge must replay the same completion order and gains exactly once.
    store.merge({"events.json": b"[]"})
    assert store.snapshot().effective_skills["TEST"]["DESIGN"] == 4


def test_simulated_completion_follows_all_uploaded_history_on_same_day(store):
    events = [event("UPLOADED"), event("CAPPED", develops_skills=[{"skill_id": "DESIGN", "gain": 1, "max_level": 2}])]
    store._state = scenario(events=events, skills={"DESIGN": 1},
                            history=[history("ZZZ_UPLOAD", "UPLOADED", "completed", "2026-10-01")])
    _, result = complete(store, "TEST", "CAPPED")
    assert result.updated_skills[0].before == 2
    assert result.updated_skills[0].after == 2


def test_missing_target_and_lead_do_not_invent_promotion():
    data = scenario(grade="Junior")  # Middle role profile is deliberately absent
    assert rank(data, data.employees["TEST"])[0] == []
    data = scenario(grade="Lead")
    assert profile(data, data.employees["TEST"]).next_grade is None


def test_zero_gap_returns_no_recommendation():
    data = scenario(skills={"DESIGN": 5, "SPEAK": 5})
    assert rank(data, data.employees["TEST"])[0] == []
