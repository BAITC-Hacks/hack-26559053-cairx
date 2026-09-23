"""Deterministic eligibility and four-factor ranking, independent of any LLM."""

from app.schemas import (
    GRADES, Achievability, Employee, Event, ExcludedEvent, Factors, GapClosure,
    HistoryFit, RankingComparison, Recommendation, RoleProfile, ScoreBreakdown, Trajectory,
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
        return Trajectory(progress_to_next_grade=0, blocking_skills=[],
                          attained_level_sum=0, required_level_sum=0)
    levels = data.effective_skills[employee.employee_id]
    required = sum(target.required_skills.values())
    attained = sum(min(levels.get(code, 0), level) for code, level in target.required_skills.items())
    return Trajectory(
        progress_to_next_grade=round(attained / required, 4) if required else 1.0,
        blocking_skills=sorted(code for code in target.critical_skills
                               if levels.get(code, 0) < target.required_skills[code]),
        attained_level_sum=attained, required_level_sum=required,
    )


def eligibility_reason(data: Dataset, employee: Employee, event: Event, *, completing=False) -> str | None:
    levels = data.effective_skills[employee.employee_id]
    history = data.history_by_employee[employee.employee_id]
    if event.mandatory:
        return "Обязательное HR-обучение не входит в добровольные рекомендации и симуляцию прогресса."
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
        reason_code = "ineligible"
        if reason is None and target is None:
            reason = "Не загружены требования для следующего грейда."
            reason_code = "missing_target"
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
                reason_code = "no_gap"
        if reason:
            excluded.append(ExcludedEvent(event_id=event.event_id, title=event.title,
                                          reason=reason, reason_code=reason_code))
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
        max_level = next(item.max_level for item in event.develops_skills if item.skill_id == primary.skill)
        factors = Factors(
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
        )
        if total <= 0:
            excluded.append(ExcludedEvent(
                event_id=event.event_id, title=event.title, reason_code="history_penalty", factors=factors,
                reason=f"Курс может сократить разрыв по навыку «{data.skills[primary.skill].name}» "
                       f"для грейда {next_grade or employee.grade}. Однако в похожих активностях "
                       f"зафиксированы пропуски/прерывания ({skipped}) и отказы ({declined}); "
                       f"штраф за историю снижает итоговый приоритет до {total}. "
                       "Поэтому сейчас эту активность не предлагаем. Причины прошлых решений "
                       "из истории неизвестны; это не оценка способностей сотрудника.",
            ))
            continue
        recommendations.append(Recommendation(
            event_id=event.event_id, title=event.title, type=event.type, duration=event.duration_hours,
            # Monotonic normalization preserves the exact raw-score ordering.
            score=round(total / (total + 100), 6),
            factors=factors,
        ))
    recommendations.sort(key=lambda item: (-item.factors.score_breakdown.total, item.event_id))
    if len(recommendations) > 3:
        cutoff = recommendations[2]
        for candidate in recommendations[3:]:
            candidate_score = candidate.factors.score_breakdown
            cutoff_score = cutoff.factors.score_breakdown
            tied = candidate_score.total == cutoff_score.total
            if tied:
                comparison = (
                    f"Приоритет совпал с «{cutoff.title}» ({candidate_score.total:g}); "
                    "для воспроизводимого порядка при равенстве используется код активности."
                )
            else:
                comparison = (
                    f"В ближайшие три шага вошли активности с более высоким суммарным приоритетом. "
                    f"У «{cutoff.title}» он {cutoff_score.total:g}, у этой активности — {candidate_score.total:g}. "
                    "Сравнение учитывает разрывы, критичность для целевого грейда, "
                    "достижимый прирост и историю участия."
                )
            excluded.append(ExcludedEvent(
                event_id=candidate.event_id, title=candidate.title, reason_code="lower_priority",
                reason=f"Активность подходит для развития навыка «{data.skills[candidate.factors.gap_closure.skill].name}», "
                       f"но пока остаётся альтернативой. {comparison}",
                factors=candidate.factors,
                compared_with=RankingComparison(
                    event_id=cutoff.event_id, title=cutoff.title,
                    score_breakdown=cutoff_score, tied=tied,
                ),
            ))
    # Surface history traps and useful alternatives before unrelated catalog entries.
    excluded.sort(key=lambda item: (
        {"history_penalty": 0, "lower_priority": 1}.get(item.reason_code, 2), item.event_id,
    ))
    return recommendations[:3], excluded
