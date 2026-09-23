"""Validated, transactional in-memory datasets. Published snapshots are read-only."""

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from threading import RLock

import pandas as pd
from pydantic import BaseModel, ValidationError

from app.schemas import Employee, Event, HistoryRecord, LoadedCounts, RoleProfile, Skill, UploadResponse

DATA_FILES = ("employees.json", "events.json", "skills.json", "activity_history.csv")
HISTORY_COLUMNS = list(HistoryRecord.model_fields)


class DataError(ValueError):
    """An invalid dataset; safe to expose to the API caller."""


@dataclass(frozen=True)
class Dataset:
    employees: dict[str, Employee]
    events: dict[str, Event]
    skills: dict[str, Skill]
    roles: dict[tuple[str, str], RoleProfile]
    history: dict[str, HistoryRecord]
    snapshot_date: date
    simulated_ids: frozenset[str] = frozenset()
    effective_skills: dict[str, dict[str, int]] = field(init=False)
    completion_gains: dict[str, dict[str, int]] = field(init=False)
    history_by_employee: dict[str, list[HistoryRecord]] = field(init=False)
    history_frame: pd.DataFrame = field(init=False, repr=False)

    def __post_init__(self):
        effective = {key: dict(emp.skills) for key, emp in self.employees.items()}
        gains = {}
        by_employee = {key: [] for key in self.employees}
        active = sorted(
            (row for row in self.history.values() if row.date <= self.snapshot_date),
            key=lambda row: (row.date, row.record_id in self.simulated_ids, row.record_id),
        )
        for row in active:
            by_employee[row.employee_id].append(row)
            if row.status != "completed":
                continue
            employee = self.employees[row.employee_id]
            event = self.events[row.event_id]
            if row.date > employee.last_review_date or row.record_id in self.simulated_ids:
                levels = effective[row.employee_id]
                gains[row.record_id] = {}
                for improvement in event.develops_skills:
                    before = levels.get(improvement.skill_id, 0)
                    after = max(before, min(before + improvement.gain, improvement.max_level))
                    levels[improvement.skill_id] = after
                    gains[row.record_id][improvement.skill_id] = after - before
            else:
                # Pre-review history has no historical skill measurements. These are catalog gains.
                gains[row.record_id] = {item.skill_id: item.gain for item in event.develops_skills}
        history_frame = pd.DataFrame([row.model_dump() for row in active], columns=HISTORY_COLUMNS)
        catalog = pd.DataFrame(
            [{"event_id": event.event_id, "event_type": event.type} for event in self.events.values()],
            columns=["event_id", "event_type"],
        )
        object.__setattr__(self, "effective_skills", effective)
        object.__setattr__(self, "completion_gains", gains)
        object.__setattr__(self, "history_by_employee", by_employee)
        object.__setattr__(self, "history_frame", history_frame.merge(catalog, on="event_id", how="left"))


def _validate_rows(model: type[BaseModel], rows, label: str, key):
    if not isinstance(rows, list):
        raise DataError(f"{label} must contain a JSON array.")
    result = {}
    for index, row in enumerate(rows):
        try:
            parsed = model.model_validate(row)
        except ValidationError as exc:
            first = exc.errors(include_input=False, include_context=False)[0]
            location = ".".join(map(str, first["loc"]))
            raise DataError(f"{label}, row {index + 1}, {location}: {first['msg']}") from exc
        identifier = key(parsed)
        if identifier in result:
            raise DataError(f"{label} contains duplicate identifier {identifier}.")
        result[identifier] = parsed
    return result


def parse_files(files: dict[str, bytes]) -> dict:
    parsed = {}
    for filename, content in files.items():
        if filename not in DATA_FILES:
            raise DataError(f"Unsupported file: {filename}. Expected: {', '.join(DATA_FILES)}.")
        try:
            text = content.decode("utf-8-sig")
            if filename == "activity_history.csv":
                reader = csv.DictReader(io.StringIO(text), strict=True)
                required = {name for name, spec in HistoryRecord.model_fields.items() if spec.is_required()}
                if not reader.fieldnames or not required <= set(reader.fieldnames):
                    raise DataError(f"activity_history.csv requires columns: {', '.join(sorted(required))}.")
                if len(reader.fieldnames) != len(set(reader.fieldnames)):
                    raise DataError("activity_history.csv contains duplicate column names.")
                rows = []
                for row in reader:
                    if None in row:
                        raise DataError("activity_history.csv contains a row with too many columns.")
                    rows.append({key: value if value != "" else None for key, value in row.items()})
                parsed["history"] = _validate_rows(HistoryRecord, rows, filename, lambda row: row.record_id)
                continue
            payload = json.loads(text)
            if filename == "skills.json":
                if not isinstance(payload, dict) or not ({"skills", "role_profiles"} & payload.keys()):
                    raise DataError("skills.json requires skills and/or role_profiles arrays.")
                if "skills" in payload:
                    parsed["skills"] = _validate_rows(Skill, payload["skills"], "skills", lambda row: row.skill_id)
                if "role_profiles" in payload:
                    parsed["roles"] = _validate_rows(
                        RoleProfile, payload["role_profiles"], "role_profiles", lambda row: (row.role, row.grade)
                    )
            else:
                collection = filename.removesuffix(".json")
                model, id_field = (Employee, "employee_id") if collection == "employees" else (Event, "event_id")
                rows = payload.get(collection) if isinstance(payload, dict) else payload
                parsed[collection] = _validate_rows(model, rows, filename, lambda row: getattr(row, id_field))
        except (UnicodeDecodeError, json.JSONDecodeError, csv.Error) as exc:
            raise DataError(f"{filename} must contain valid UTF-8 {'CSV' if filename.endswith('.csv') else 'JSON'}.") from exc
    return parsed


def validate_relations(data: dict, snapshot_date: date) -> list[str]:
    skills, roles, employees, events = (data[key] for key in ("skills", "roles", "employees", "events"))
    warnings = []

    def require_skills(codes, label):
        missing = set(codes) - skills.keys()
        if missing:
            raise DataError(f"{label} references unknown skills: {', '.join(sorted(missing))}.")

    for profile in roles.values():
        require_skills(profile.required_skills, f"{profile.role}/{profile.grade}")
    for employee in employees.values():
        require_skills(employee.skills, employee.employee_id)
        if (employee.role, employee.grade) not in roles:
            raise DataError(f"{employee.employee_id} has no role profile for {employee.role}/{employee.grade}.")
        if employee.last_review_date > snapshot_date:
            raise DataError(f"{employee.employee_id}: last_review_date is after the snapshot date.")
        if employee.hire_date and employee.hire_date > snapshot_date:
            raise DataError(f"{employee.employee_id}: hire_date is after the snapshot date.")
        if employee.manager_id and employee.manager_id not in employees:
            warnings.append(f"{employee.employee_id}: manager {employee.manager_id} is not loaded.")
    for event in events.values():
        require_skills(event.prerequisites, event.event_id)
        require_skills((item.skill_id for item in event.develops_skills), event.event_id)
    for row in data["history"].values():
        if row.employee_id not in employees or row.event_id not in events:
            raise DataError(f"History {row.record_id} references an unknown employee or event.")
        if row.date > snapshot_date:
            warnings.append(f"History {row.record_id} is after the snapshot date and is ignored until then.")
    return sorted(warnings)


class DataStore:
    def __init__(self, data_path: Path, snapshot_date: date):
        self.data_path = data_path
        self.snapshot_date = snapshot_date
        self.lock = RLock()
        self._state: Dataset | None = None

    def snapshot(self) -> Dataset:
        with self.lock:
            if self._state is None:
                raise RuntimeError("Dataset has not been loaded.")
            return self._state

    def reset(self) -> Dataset:
        with self.lock:
            parsed = parse_files({name: (self.data_path / name).read_bytes() for name in DATA_FILES})
            validate_relations(parsed, self.snapshot_date)
            state = Dataset(**parsed, snapshot_date=self.snapshot_date)
            self._state = state
            return state

    def merge(self, files: dict[str, bytes]) -> UploadResponse:
        incoming = parse_files(files)
        with self.lock:
            old = self.snapshot()
            merged = {key: {**getattr(old, key), **incoming.get(key, {})}
                      for key in ("employees", "events", "skills", "roles", "history")}
            warnings = validate_relations(merged, self.snapshot_date)
            for key, rows in incoming.items():
                replaced = rows.keys() & getattr(old, key).keys()
                if replaced:
                    warnings.append(f"Updated {len(replaced)} existing {key} record(s) by identifier.")
            simulated = frozenset(
                record_id for record_id in old.simulated_ids
                if record_id not in incoming.get("history", {})
                and old.history[record_id].employee_id not in incoming.get("employees", {})
            )
            self._state = Dataset(**merged, snapshot_date=self.snapshot_date, simulated_ids=simulated)
        return UploadResponse(
            loaded=LoadedCounts(
                employees=len(incoming.get("employees", {})), events=len(incoming.get("events", {})),
                skills=len(incoming.get("skills", {})), role_profiles=len(incoming.get("roles", {})),
                history_rows=len(incoming.get("history", {})),
            ),
            employee_ids=sorted(incoming.get("employees", {})), warnings=sorted(warnings),
        )

    def record_completion(self, employee_id: str, event_id: str) -> Dataset:
        """Caller holds lock while checking eligibility and publishing the completion."""
        old = self.snapshot()
        pending = [row for row in old.history_by_employee[employee_id]
                   if row.event_id == event_id and row.status in ("in_progress", "overdue")]
        history = dict(old.history)
        sequence = 1
        while f"SIM_{sequence:08d}" in history:
            sequence += 1
        record_id = f"SIM_{sequence:08d}"
        if pending:
            latest = max(pending, key=lambda row: (row.date, row.record_id))
            # Use a monotonic ID so multiple same-day completions replay in completion order.
            row = latest.model_copy(update={
                "record_id": record_id, "date": self.snapshot_date,
                "status": "completed", "completion_pct": 100,
            })
            del history[latest.record_id]
        else:
            row = HistoryRecord(
                record_id=record_id, employee_id=employee_id, event_id=event_id,
                date=self.snapshot_date, status="completed", completion_pct=100,
            )
        history[record_id] = row
        self._state = Dataset(
            employees=old.employees, events=old.events, skills=old.skills, roles=old.roles,
            history=history, snapshot_date=self.snapshot_date,
            simulated_ids=old.simulated_ids | {record_id},
        )
        return self._state
