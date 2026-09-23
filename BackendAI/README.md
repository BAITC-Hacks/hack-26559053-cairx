# Career Quest backend

Backend requirements are in `Files/Info`, `Files/Info2` and `Files/structure`.
The supplied dataset contains 200 employees, 40 activities, 60 skills, 32 role
profiles and 2,743 history records. All date calculations use `2026-10-01` by default.

## Data and scoring

`app/services/loader.py` validates the four input files with Pydantic and stores
them in memory. Uploads merge by employee/event/skill/record ID and by
`(role, grade)` for role profiles. Every batch validates before publishing a
new snapshot; invalid batches leave the previous dataset intact. CSV history is
joined with the event catalog using Pandas. Original dataset files are never edited.

Employee levels start at the last review, then replay completed activities after
that review chronologically, capped by each activity's `max_level`. Earlier
completions are already reflected in the assessment and are not applied again.
Missing skills have level zero. `skills_gained` in older, pre-review history is
the catalog gain, since actual historical before/after levels are not supplied.

The target is the next grade in the employee's current role. Leads close remaining
gaps against Lead requirements, with `next_grade: null`. A career goal does not
override this progression. Courses must match role, current grade, prerequisites,
and available sessions (self-paced courses are always available). Mandatory,
completed, in-progress and fully capped courses are excluded. `EV_036` is the
dataset's repeatable club; it can be completed once per snapshot day.

For each useful skill, scoring adds `10 * gap`, `10 * min(actual gain, gap)`,
and a 20-point critical-skill bonus. Each dropped, missed or declined similar
activity subtracts 30 points. Similar means the same event type OR an overlapping
skill; a history row is counted only once. Nonpositive scores are excluded.
The top three sort by descending raw score, then ascending event ID. Public
scores are `raw / (raw + 100)`; exact components are returned in `factors`.
No LLM participates in eligibility, skill calculations or ranking.

HR statistics use effective skill levels and role requirements. Participation
rate is completed / (completed + dropped + no_show + declined); unresolved and
mandatory-overdue records do not enter that denominator.
