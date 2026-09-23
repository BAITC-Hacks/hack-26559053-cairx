from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=120)]
Level = Annotated[int, Field(ge=0, le=5)]
Grade = Literal["Junior", "Middle", "Senior", "Lead"]
GRADES = ("Junior", "Middle", "Senior", "Lead")


class InputModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore", allow_inf_nan=False)


class Skill(InputModel):
    skill_id: Identifier
    name: str = Field(min_length=1)
    type: Literal["hard", "soft"]
    category: str = ""
    description: str = ""


class RoleProfile(InputModel):
    role: Identifier
    grade: Grade
    required_skills: dict[Identifier, Level]
    critical_skills: list[Identifier] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_critical(self):
        if not set(self.critical_skills) <= self.required_skills.keys():
            raise ValueError("critical_skills must be included in required_skills")
        return self


class CareerGoal(InputModel):
    target_role: Identifier
    target_grade: Grade


class Employee(InputModel):
    employee_id: Identifier
    full_name: str = Field(min_length=1, validation_alias=AliasChoices("full_name", "name"))
    role: Identifier
    grade: Grade
    skills: dict[Identifier, Level]
    department: str = ""
    manager_id: Identifier | None = None
    hire_date: date | None = None
    tenure_months: int = Field(default=0, ge=0)
    work_format: Literal["office", "hybrid", "remote"] = "office"
    preferred_language: Literal["kk", "ru", "en"] = "ru"
    career_goal: CareerGoal | None = None
    last_review_date: date


class SkillGain(InputModel):
    skill_id: Identifier
    gain: int = Field(gt=0, le=5)
    max_level: Level


class Event(InputModel):
    event_id: Identifier
    title: str = Field(min_length=1)
    description: str = ""
    type: Identifier
    format: Literal["online", "offline", "self_paced"]
    duration_hours: float = Field(ge=0)
    mandatory: bool
    target_roles: list[Identifier] = Field(default_factory=list)
    target_grades: list[Grade] = Field(default_factory=list)
    develops_skills: list[SkillGain]
    prerequisites: dict[Identifier, Level] = Field(default_factory=dict)
    upcoming_sessions: list[date] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_gains(self):
        codes = [gain.skill_id for gain in self.develops_skills]
        if len(codes) != len(set(codes)):
            raise ValueError("develops_skills contains duplicate skills")
        return self


class HistoryRecord(InputModel):
    record_id: Identifier
    employee_id: Identifier
    event_id: Identifier
    date: date
    due_date: date | None = None
    status: Literal["completed", "in_progress", "dropped", "no_show", "declined", "overdue"]
    completion_pct: int = Field(ge=0, le=100)
    score: int | None = Field(default=None, ge=0, le=100)
    feedback_rating: int | None = Field(default=None, ge=1, le=5)
    assigned_by: Literal["self", "manager", "hr"] = "self"

    @model_validator(mode="after")
    def completion_matches_status(self):
        if self.status == "completed" and self.completion_pct != 100:
            raise ValueError("Completed activities must have completion_pct=100")
        if self.status in ("no_show", "declined") and self.completion_pct != 0:
            raise ValueError("Skipped or declined activities must have completion_pct=0")
        return self


class RecommendRequest(InputModel):
    employee_id: Identifier


class CompleteRequest(RecommendRequest):
    event_id: Identifier


class Trajectory(BaseModel):
    progress_to_next_grade: float
    blocking_skills: list[str]


class EmployeeSummary(BaseModel):
    employee_id: str
    name: str
    role: str
    grade: str
    tenure_months: int
    has_recommendation: bool


class SkillProgress(BaseModel):
    code: str
    name: str
    current: int
    required_next: int | None
    gap: int
    type: str
    critical: bool


class CompletedActivity(BaseModel):
    event_id: str
    title: str
    completed_at: date
    skills_gained: dict[str, int]


class HistoryStats(BaseModel):
    attended: int
    skipped: int
    declined: int


class EmployeeProfile(EmployeeSummary):
    next_grade: str | None
    skills: list[SkillProgress]
    completed_activities: list[CompletedActivity]
    history_stats: HistoryStats
    trajectory: Trajectory


class GapClosure(BaseModel):
    skill: str
    current: int
    required: int
    gain: int


class HistoryFit(BaseModel):
    similar_attended: int
    similar_skipped: int
    similar_declined: int
    note: str


class Achievability(BaseModel):
    max_level: int
    reachable: bool


class ScoreBreakdown(BaseModel):
    gap: float
    achievability: float
    criticality: float
    history_penalty: float
    total: float


class Factors(BaseModel):
    gap_closure: GapClosure
    grade_criticality: str
    history_fit: HistoryFit
    achievability: Achievability
    skill_gains: list[GapClosure]
    score_breakdown: ScoreBreakdown


class Recommendation(BaseModel):
    event_id: str
    title: str
    type: str
    duration: float
    score: float
    factors: Factors
    explanation: str = Field(default="", description="Narrative explaining practical benefit, grade relevance and history.")
    explanation_source: Literal["openai", "nvidia", "template"] = "template"
    explanation_model: str | None = None
    explanation_cached: bool = Field(default=False, description="True when reusing a previously generated LLM explanation.")
    explanation_fallback_reason: Literal[
        "not_configured", "timeout", "authentication", "rate_limit", "provider_error", "invalid_response"
    ] | None = None


class ExcludedEvent(BaseModel):
    event_id: str
    title: str
    reason: str


class RecommendationResponse(BaseModel):
    employee_id: str
    generated_at: datetime
    llm_used: bool = Field(description="At least one card uses LLM-generated text, including cached text; inspect each card's explanation_source.")
    recommendations: list[Recommendation]
    not_recommended: list[ExcludedEvent]


class UpdatedSkill(BaseModel):
    code: str
    before: int
    after: int
    max_level: int


class CompletionTrajectory(Trajectory):
    previous_progress_to_next_grade: float


class CompleteResponse(BaseModel):
    employee_id: str
    event_id: str
    updated_skills: list[UpdatedSkill]
    trajectory: CompletionTrajectory
    new_recommendations: list[Recommendation]
    llm_used: bool


class LoadedCounts(BaseModel):
    employees: int = 0
    events: int = 0
    skills: int = 0
    role_profiles: int = 0
    history_rows: int = 0


class UploadResponse(BaseModel):
    loaded: LoadedCounts
    employee_ids: list[str]
    warnings: list[str]


class WeakSkill(BaseModel):
    code: str
    name: str
    avg_level: float
    required_avg: float
    employees_below: int


class NoRecommendation(BaseModel):
    employee_id: str
    name: str
    role: str
    reason: str


class Participation(BaseModel):
    event_id: str
    title: str
    attended: int
    skipped: int
    declined: int
    rate: float


class Totals(BaseModel):
    employees: int
    with_gaps: int


class Overview(BaseModel):
    weakest_skills: list[WeakSkill]
    no_recommendation: list[NoRecommendation]
    activity_participation: list[Participation]
    totals: Totals
