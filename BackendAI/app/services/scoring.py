"""Deterministic eligibility and four-factor ranking, independent of any LLM."""

from app.schemas import (
    GRADES, Achievability, Employee, Event, ExcludedEvent, Factors, GapClosure,
    HistoryFit, Recommendation, RoleProfile, ScoreBreakdown, Trajectory,
)
from app.services.loader import Dataset

REPEATABLE_EVENTS = frozenset({"EV_036"})
NEGATIVE_STATUSES = frozenset({"dropped", "no_show", "declined"})


def target_profile(data: Dataset, employee: Employee) -> tuple[str | None, RoleProfile | None]:
    index = GRADES.index(employee.grade)
    if index == len(GRADES) - 1:
        # Leads can still close gaps against their current role requirements.
        return None, data.roles.get((employee.role, employee.grade))
    next_grade = GRADES[index + 1]
    return next_grade, data.roles.get((employee.role, next_grade))


def trajectory(data: Dataset, employee: Employee) -> Trajectory:
    _, target = target_profile(data, employee)
    if target is None:
        return Trajectory(progress_to_next_grade=0, blocking_skills=[])
    levels = data.effective_skills[employee.employee_id]
    required = sum(target.required_skills.values())
    attained = sum(min(levels.get(code, 0), level) for code, level in target.required_skills.items())
    return Trajectory(
        progress_to_next_grade=round(attained / required, 4) if required else 1.0,
        blocking_skills=sorted(code for code in target.critical_skills
                               if levels.get(code, 0) < target.required_skills[code]),
    )


def eligibility_reason(data: Dataset, employee: Employee, event: Event, *, completing=False) -> str | None:
    levels = data.effective_skills[employee.employee_id]
    history = data.history_by_employee[employee.employee_id]
    if event.mandatory and not completing:
        return "Обязательное HR-обучение не входит в рекомендации."
    completed = [row for row in history if row.event_id == event.event_id and row.status == "completed"]
    if completed and event.event_id not in REPEATABLE_EVENTS:
        return "Активность уже пройдена."
    if completed and event.event_id in REPEATABLE_EVENTS and any(row.date == data.snapshot_date for row in completed):
        return "Эта сессия клуба уже пройдена в дату среза."
    if not completing and any(row.event_id == event.event_id and row.status == "in_progress" for row in history):
        return "Активность уже в процессе выполнения."
    if event.target_roles and employee.role not in event.target_roles:
        return "Активность рассчитана на другую роль."
    if event.target_grades and employee.grade not in event.target_grades:
        return "Активность рассчитана на другой грейд."
    missing = [code for code, required in event.prerequisites.items() if levels.get(code, 0) < required]
    if missing:
        return "Не выполнены предварительные требования: " + ", ".join(sorted(missing)) + "."
    if not completing and event.format != "self_paced" and not any(day >= data.snapshot_date for day in event.upcoming_sessions):
        return "Нет доступных сессий на дату среза или позже."
    if not completing and not any(levels.get(item.skill_id, 0) < item.max_level for item in event.develops_skills):
        return "Активность не повысит навыки: достигнут потолок курса или нет развиваемых навыков."
    return None


def rank(data: Dataset, employee: Employee) -> tuple[list[Recommendation], list[ExcludedEvent]]:
    next_grade, target = target_profile(data, employee)
    levels = data.effective_skills[employee.employee_id]
    history = data.history_by_employee[employee.employee_id]
    recommendations, excluded = [], []
    for event in sorted(data.events.values(), key=lambda item: item.event_id):
        reason = eligibility_reason(data, employee, event)
        if reason is None and target is None:
            reason = "Не загружены требования для следующего грейда."
        improvements = []
        if reason is None:
            for item in event.develops_skills:
                current = levels.get(item.skill_id, 0)
                required = target.required_skills.get(item.skill_id, 0)
                gain = min(item.gain, max(0, item.max_level - current))
                if current < required and gain > 0:
                    improvements.append(GapClosure(skill=item.skill_id, current=current, required=required, gain=gain))
            if not improvements:
                reason = "Активность не сокращает разрывы по требованиям целевого грейда."
        if reason:
            excluded.append(ExcludedEvent(event_id=event.event_id, title=event.title, reason=reason))
            continue

        improvements.sort(key=lambda item: (
            item.skill not in target.critical_skills, -(item.required - item.current), item.skill,
        ))
        primary = improvements[0]
        developed = {item.skill_id for item in event.develops_skills}
        similar = []
        for row in history:
            past = data.events[row.event_id]
            if past.type == event.type or developed.intersection(item.skill_id for item in past.develops_skills):
                similar.append(row)
        attended = sum(row.status == "completed" for row in similar)
        skipped = sum(row.status in ("dropped", "no_show") for row in similar)
        declined = sum(row.status == "declined" for row in similar)
        gap_score = 10 * sum(item.required - item.current for item in improvements)
        gain_score = 10 * sum(min(item.gain, item.required - item.current) for item in improvements)
        criticality = 20 * sum(item.skill in target.critical_skills for item in improvements)
        penalty = 30 * (skipped + declined)
        total = gap_score + gain_score + criticality - penalty
        if total <= 0:
            excluded.append(ExcludedEvent(
                event_id=event.event_id, title=event.title,
                reason=f"Похожие активности: {skipped} пропусков/прерываний и {declined} отказов; "
                       f"штраф за историю {penalty} снижает оценку до {total}.",
            ))
            continue
        max_level = next(item.max_level for item in event.develops_skills if item.skill_id == primary.skill)
        recommendations.append(Recommendation(
            event_id=event.event_id, title=event.title, type=event.type, duration=event.duration_hours,
            # Monotonic normalization preserves the exact raw-score ordering.
            score=round(total / (total + 100), 6),
            factors=Factors(
                gap_closure=primary,
                grade_criticality=(f"critical_for_{next_grade or employee.grade}"
                                   if primary.skill in target.critical_skills else "development"),
                history_fit=HistoryFit(
                    similar_attended=attended, similar_skipped=skipped, similar_declined=declined,
                    note=f"Пройдено похожих: {attended}; пропущено/брошено: {skipped}; отказов: {declined}.",
                ),
                achievability=Achievability(max_level=max_level, reachable=True),
                skill_gains=improvements,
                score_breakdown=ScoreBreakdown(
                    gap=gap_score, achievability=gain_score, criticality=criticality,
                    history_penalty=penalty, total=total,
                ),
            ),
        ))
    recommendations.sort(key=lambda item: (-item.factors.score_breakdown.total, item.event_id))
    return recommendations[:3], excluded
