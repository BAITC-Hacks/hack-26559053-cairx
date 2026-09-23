"""Atomic completion and immediately recalculated trajectory."""

from fastapi import HTTPException

from app.schemas import CompleteResponse, CompletionTrajectory, UpdatedSkill
from app.services.loader import DataStore, Dataset
from app.services.scoring import eligibility_reason, rank, trajectory


def complete(store: DataStore, employee_id: str, event_id: str) -> tuple[Dataset, CompleteResponse]:
    with store.lock:
        old = store.snapshot()
        employee = old.employees.get(employee_id)
        event = old.events.get(event_id)
        if employee is None:
            raise HTTPException(404, "Employee not found.")
        if event is None:
            raise HTTPException(404, "Event not found.")
        reason = eligibility_reason(old, employee, event, completing=True)
        if reason:
            raise HTTPException(409, reason)
        before = old.effective_skills[employee_id]
        previous = trajectory(old, employee)
        updated = store.record_completion(employee_id, event_id)
        after = updated.effective_skills[employee_id]
        result = CompleteResponse(
            employee_id=employee_id, event_id=event_id,
            updated_skills=[UpdatedSkill(
                code=item.skill_id, before=before.get(item.skill_id, 0),
                after=after.get(item.skill_id, 0), max_level=item.max_level,
            ) for item in event.develops_skills],
            trajectory=CompletionTrajectory(
                **trajectory(updated, employee).model_dump(),
                previous_progress_to_next_grade=previous.progress_to_next_grade,
            ),
            new_recommendations=rank(updated, employee)[0], llm_used=False,
        )
        return updated, result
