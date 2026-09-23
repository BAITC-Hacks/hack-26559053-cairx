"""Employee projections and HR statistics from one consistent dataset snapshot."""

from app.schemas import (
    CompletedActivity, Employee, EmployeeProfile, EmployeeSummary, HistoryStats,
    NoRecommendation, Overview, Participation, SkillProgress, Totals, WeakSkill,
)
from app.services.loader import Dataset
from app.services.scoring import rank, target_profile, trajectory


def tenure_months(data: Dataset, employee: Employee) -> int:
    if employee.hire_date is None:
        return employee.tenure_months
    today, hired = data.snapshot_date, employee.hire_date
    return max(0, (today.year - hired.year) * 12 + today.month - hired.month - (today.day < hired.day))


def summary(data: Dataset, employee: Employee) -> EmployeeSummary:
    return EmployeeSummary(
        employee_id=employee.employee_id, name=employee.full_name, role=employee.role,
        grade=employee.grade, tenure_months=tenure_months(data, employee),
        has_recommendation=bool(rank(data, employee)[0]),
    )


def profile(data: Dataset, employee: Employee) -> EmployeeProfile:
    next_grade, target = target_profile(data, employee)
    required = target.required_skills if target else {}
    critical = set(target.critical_skills) if target else set()
    levels = data.effective_skills[employee.employee_id]
    skills = [SkillProgress(
        code=code, name=data.skills[code].name, current=levels.get(code, 0), required_next=required.get(code),
        gap=max(0, required.get(code, 0) - levels.get(code, 0)), type=data.skills[code].type,
        critical=code in critical,
    ) for code in levels.keys() | required.keys()]
    skills.sort(key=lambda item: (not item.critical, -item.gap, item.code))
    history = data.history_by_employee[employee.employee_id]
    completed = [CompletedActivity(
        event_id=row.event_id, title=data.events[row.event_id].title, completed_at=row.date,
        skills_gained=data.completion_gains[row.record_id],
    ) for row in reversed(history) if row.status == "completed"]
    return EmployeeProfile(
        **summary(data, employee).model_dump(), next_grade=next_grade, skills=skills,
        completed_activities=completed,
        history_stats=HistoryStats(
            attended=sum(row.status == "completed" for row in history),
            skipped=sum(row.status in ("dropped", "no_show") for row in history),
            declined=sum(row.status == "declined" for row in history),
        ), trajectory=trajectory(data, employee),
    )


def overview(data: Dataset) -> Overview:
    skill_values = {}
    no_recommendation = []
    with_gaps = 0
    for employee in sorted(data.employees.values(), key=lambda item: item.employee_id):
        _, target = target_profile(data, employee)
        levels = data.effective_skills[employee.employee_id]
        if target:
            has_gap = False
            for code, required in target.required_skills.items():
                current = levels.get(code, 0)
                skill_values.setdefault(code, []).append((current, required))
                has_gap |= current < required
            with_gaps += has_gap
        recommendations, excluded = rank(data, employee)
        if not recommendations:
            if target is None:
                reason = "Не загружены требования для следующего грейда."
            elif not any(levels.get(code, 0) < value for code, value in target.required_skills.items()):
                reason = "Все требования целевого грейда уже выполнены."
            else:
                history_reasons = [item.reason for item in excluded if item.reason_code == "history_penalty"]
                reason = history_reasons[0] if history_reasons else "Нет доступных активностей для оставшихся разрывов."
            no_recommendation.append(NoRecommendation(
                employee_id=employee.employee_id, name=employee.full_name, role=employee.role, reason=reason,
            ))
    weakest = [WeakSkill(
        code=code, name=data.skills[code].name,
        avg_level=round(sum(current for current, _ in values) / len(values), 4),
        required_avg=round(sum(required for _, required in values) / len(values), 4),
        employees_below=sum(current < required for current, required in values),
    ) for code, values in skill_values.items()]
    weakest.sort(key=lambda item: (-item.employees_below, -(item.required_avg - item.avg_level), item.code))
    counts = data.history_frame.groupby(["event_id", "status"]).size().to_dict()
    participation = []
    for event in sorted(data.events.values(), key=lambda item: item.event_id):
        attended = int(counts.get((event.event_id, "completed"), 0))
        skipped = int(counts.get((event.event_id, "dropped"), 0) + counts.get((event.event_id, "no_show"), 0))
        declined = int(counts.get((event.event_id, "declined"), 0))
        resolved = attended + skipped + declined
        participation.append(Participation(
            event_id=event.event_id, title=event.title, attended=attended, skipped=skipped,
            declined=declined, rate=round(attended / resolved, 4) if resolved else 0.0,
        ))
    return Overview(
        weakest_skills=weakest, no_recommendation=no_recommendation, activity_participation=participation,
        totals=Totals(employees=len(data.employees), with_gaps=with_gaps),
    )
