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

Every catalog activity appears exactly once in either `recommendations` or
`not_recommended`. Exclusions have a stable `reason_code`: `ineligible`,
`missing_target`, `no_gap`, `history_penalty`, or `lower_priority`. Scored but
rejected candidates retain the same numeric `factors` as selected candidates;
hard exclusions have `factors: null` rather than a made-up score. Positive
candidates outside the top three expose `compared_with`, containing the last
selected activity and its score components. Equal scores explicitly report a
tie; event ID determines order without claiming one candidate is better.
History exclusions and scored alternatives appear first, then other exclusions,
with stable event-ID ordering within each group. Exclusion text is deterministic
and needs no LLM. History lowers an activity's priority, not an employee rating.

Trajectory progress is `sum(min(current, required)) / sum(required)` across
target skills, rounded to four decimals. `attained_level_sum` and
`required_level_sum` expose that numerator and denominator. Excess proficiency
in one skill cannot compensate for another skill's gap. An empty set of known
requirements is fully covered; missing target requirements yield zero progress.
This is requirement coverage, not a promotion probability or an awarded grade.

HR statistics use effective skill levels and role requirements. Participation
rate is completed / (completed + dropped + no_show + declined); unresolved and
mandatory-overdue records do not enter that denominator.

## Run the backend

Python 3.12+ is supported. From `BackendAI`:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe run.py
```

On Linux/macOS the equivalent interpreter is `.venv/bin/python`.
The API listens on `http://localhost:8000`, serves the frontend at `/` and
`/static/`, with interactive docs at `/docs` and OpenAPI at
`/api/v1/openapi.json`. Startup fails clearly if a required dataset file is
missing or invalid. From the repository root, `docker compose up --build`
builds and starts the same application on port 8000.

## Configuration

Settings come from the process environment; the application itself does not
load `.env` files. Docker Compose loads an optional root `.env` file into the
container. `BackendAI/.env.example` lists example values. For a local run, set
`$env:OPENAI_API_KEY = "..."` in PowerShell before starting the process.
Never commit keys or `.env` files.

### Enable live LLM explanations locally

Create an API key using the [OpenAI setup instructions](https://developers.openai.com/api/docs/quickstart).
From the repository root, run this in your own PowerShell terminal:

```powershell
BackendAI/.venv/Scripts/python.exe BackendAI/run.py --llm openai
```

Paste the key into the hidden terminal prompt and press Enter. The launcher
sets `OPENAI_API_KEY` for this server process before loading settings. It does
not write the key to disk or change your persistent Windows environment.
An already configured environment key is reused. For NVIDIA use `--llm nvidia`;
for both providers use `--llm both`. Running without `--llm` retains the normal
environment-only startup. A `.env` entry alone does not enable a provider.

To save the key as a persistent **Windows user environment variable**, run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File BackendAI/set_llm_env.ps1
```

The script asks for the key with hidden input and saves `OPENAI_API_KEY` using
Windows user environment settings. For NVIDIA, add `-Provider nvidia`.
It does not save the key in repository files. Blank input leaves the existing
variable unchanged. Restart VS Code and the backend after saving; already
running processes retain their old environment. You can then launch normally:

```powershell
BackendAI/.venv/Scripts/python.exe BackendAI/run.py
```

With the server running, check a real recommendation from a second terminal:

```powershell
Invoke-RestMethod -Uri http://localhost:8000/api/recommend -Method Post -ContentType application/json -Body '{"employee_id":"E0001"}' | ConvertTo-Json -Depth 10
```

`llm_used: true` and `explanation_source: "openai"` (or `"nvidia"`) confirm
successful live generation. `llm_used: false` means the local fallback was used;
check the server log for the provider error class. `/api/health` only confirms
that a provider was configured; it does not validate the key or API access.

| Variable | Default / meaning |
| --- | --- |
| `OPENAI_API_KEY`, `NVIDIA_API_KEY` | Optional; no keys means fully local explanations |
| `OPENAI_MODEL` | `gpt-4o-mini` |
| `NVIDIA_MODEL` | `meta/llama-3.1-70b-instruct` |
| `LLM_TIMEOUT_SECONDS` | 8 seconds maximum per provider; no automatic retries |
| `LLM_TOTAL_TIMEOUT_SECONDS` | 9 seconds shared by all explanation calls and provider fallbacks; maximum 9 |
| `DATA_DIR` | `dataset`, resolved relative to BackendAI, or an absolute path |
| `SNAPSHOT_DATE` | `2026-10-01`, used for tenure, history and session eligibility |
| `MAX_UPLOAD_BYTES` | 10 MiB total file content per upload batch |
| `HOST`, `PORT` | `0.0.0.0`, `8000` |
| `DEBUG` | `false`; enables reload/debug logging when true |
| `CORS_ORIGINS` | `*`, or comma-separated origins / JSON array |
| `API_V1_STR` | `/api/v1`, compatibility prefix and OpenAPI location |

## API

Canonical routes use `/api`. All routes also have aliases under `API_V1_STR`.

| Method and route | Request / behavior |
| --- | --- |
| `GET /api/health` | Status, loaded employee count, snapshot date, configured LLM availability |
| `GET /api/employees` | Optional `search`, `role`, `grade`, `limit` (default 50, maximum 1000) |
| `GET /api/employees/{employee_id}` | Effective skills, next-grade gaps, completed activities, history statistics and trajectory |
| `POST /api/recommend` | JSON `{"employee_id":"E0001"}`; up to three ranked cards, factors and exclusion reasons |
| `POST /api/complete` | JSON `{"employee_id":"E0001","event_id":"EV_005"}`; before/after levels, trajectory and fresh recommendations |
| `GET /api/hr/overview` | Weak skills, employees without recommendations, participation and totals |
| `POST /api/upload` | Multipart `files` or `files[]`; any subset of the four named dataset files |
| `POST /api/reset` | Discards in-memory changes and reloads the original files |

`POST /api/recommend/{employee_id}` and
`POST /api/complete/{employee_id}/{event_id}` are path-parameter aliases. Both
use the full `Info2` response objects, including `explanation`, rather than the
older short response examples in `Info`. Durations are in hours; trajectory
progress is a ratio between 0 and 1. `generated_at` records the actual UTC
request time; domain calculations use the fixed snapshot date.

JSON input accepts dataset wrappers (`{"employees":[...]}`, `{"events":[...]}`)
or bare arrays. `skills.json` accepts `skills` and/or `role_profiles` arrays.
CSV accepts UTF-8 with or without BOM; optional blank values become null.
Unknown skill/history references, invalid schemas and duplicate IDs within one
file reject the entire upload. Existing IDs update in place; other records stay
loaded. Warnings report replaced IDs, missing managers and future history.
Future history is retained but does not affect this snapshot's recommendations.

Completion is serialized with uploads/reset, applies gains without reducing any
skill above a course's ceiling, and rejects repeated completion with HTTP 409.
Mandatory activities also return HTTP 409: voluntary completion simulation
cannot award progress for compulsory processes. Real mandatory history remains
visible in profiles and HR statistics; catalog skill gains recorded after a
review remain part of the supplied assessment model, without recommendation
points, rewards or employee rankings.
An in-progress enrollment becomes a completion with a new simulation record ID.
Completion at the review date still applies its gains once. A new uploaded
employee assessment takes precedence over simulated review-day adjustments.

Validation errors return HTTP 422, unknown employees/events return 404,
and uploads above the content limit return 413. Errors have
`{"success":false,"error_code":"...","detail":"..."}`; request validation
also supplies field-level `errors`. Internal errors do not expose exception text.

## Explanations

Each selected course gets a short Russian paragraph explaining practical benefit,
relevance to the employee's role and target grade, expected progress, and what
participation history supports. The prompt includes actual course content and skill
descriptions from the dataset. Python translates calculated levels/gains/ceilings
into explicit outcomes (closing a skill gap versus only reducing it), rather than
asking the LLM to recalculate them or repeat a table of numbers. The exact numeric
factors remain unchanged in the API. Python appends a history sentence from the
recorded counts to the LLM's practical/career paragraph, so that this fact-sensitive
part is not left for the model to infer. Missing history is distinguished from
lack of experience; no on-time completion claims are inferred from counts.

Up to three card explanations run concurrently. Each tries OpenAI, then NVIDIA,
then a local narrative template. Both providers use `temperature=0` and zero
retries. The default per-provider timeout is eight seconds, with a shared nine-second
deadline across all cards and providers. OpenAI uses a strict JSON schema for one
`explanation` string. NVIDIA uses JSON instructions with the same local validation.
Invalid JSON/fields, blank text, truncated responses and timeouts trigger fallback.
The local template also explains grade relevance, course content and history.

Successful LLM paragraphs are cached in memory for five minutes (up to 128 entries).
The cache key covers all prompt facts and provider/model choices, so changed skills,
history, target requirements or uploaded course descriptions cannot reuse stale text.
Fallbacks are never cached. Employee names and IDs are not sent to the providers.
No external API is called without a configured key, or for an empty ranking.

`llm_used` is true when at least one card has LLM-generated text, including cached
text. Each card exposes `explanation_source`, `explanation_model`,
`explanation_cached` and `explanation_fallback_reason`. Fallback reasons are
`not_configured`, `timeout`, `authentication`, `rate_limit`, `provider_error`, or
`invalid_response`; successful cards have a null reason. Inspect these fields to
distinguish fresh generation, reuse and fallback. Mixed responses can contain both
LLM and template cards. Safe provider outcome logs contain no keys or employee data.
`/health` reports configured clients, not a live provider probe.
The providers never control scores or ordering. Generated prose is not fully
semantically verified; the numeric factors remain authoritative.

The implementation uses the documented
[GPT-4o mini Chat Completions endpoint](https://developers.openai.com/api/docs/models/gpt-4o-mini)
and [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat).
No external provider is needed for the test suite.

## Проверка критериев жюри

Все сценарии ниже проверяются через `/docs`, без аккаунтов команды и без ключа
LLM: в этом случае текст формируется локально, `llm_used: false`.

| Критерий | Как проверить backend |
| --- | --- |
| Профиль и траектория | `GET /api/employees/E0001`: роль, грейд, навыки, разрывы, завершённые активности, числитель и знаменатель прогресса |
| 1–3 релевантные активности | `POST /api/recommend` с `employee_id`: скоринг по четырём факторам; при отсутствии подходящих вариантов список пуст |
| Объяснение | `explanation`, `factors.score_breakdown`, `not_recommended[].reason` и числовые факторы отвергнутых кандидатов |
| Обновление прогресса | `POST /api/complete` для выбранного шага: уровни `before/after`, прежняя и новая траектория, пересчитанные рекомендации |
| HR-view | `GET /api/hr/overview`: дефициты навыков, причины отсутствия шагов, участие по активностям |
| Произвольные профили жюри | `POST /api/upload`: профили и история мержатся с текущими данными; затем доступны обычные маршруты профиля и рекомендаций |

В `tests/fixtures/jury/` находятся **искусственные проверочные профили**, а не
производственные данные или заранее подготовленные ответы. Они используют
исходный каталог активностей и требования ролей, автоматически не загружаются.
Алгоритм не содержит специальных условий для их идентификаторов.

1. В `/docs` откройте `POST /api/upload`, нажмите **Try it out** и добавьте в
   поле `files` оба файла из `tests/fixtures/jury/`: `employees.json` и
   `activity_history.csv`. После загрузки должно быть 203 сотрудника.
2. Вызовите `/api/recommend` для `JURY_HISTORY_TRAP`. У него Public Speaking
   равен 0, System Design — 3 при требуемых 4 для Senior. Три пропуска клуба
   исключают `EV_036`: в `not_recommended` видны `reason_code: history_penalty`,
   `similar_skipped: 3` и компоненты `20 + 10 + 0 - 90 = -60`. Выбраны
   `EV_006` и `EV_007`, развивающие критичный System Design; оценка каждой —
   `10 + 10 + 20 - 0 = 40`. Базовый курс `EV_005` исключён из-за потолка навыка.
3. Для `JURY_NO_HISTORY` навыки **те же**, но пропусков нет: `EV_036` входит
   третьим шагом с оценкой `20 + 10 = 30`. Это проверяет влияние истории при
   неизменном профиле навыков, а не правило «брать самый низкий навык».
4. У `JURY_REQUIREMENTS_MET` нет разрывов: рекомендаций нет, и HR-срез
   показывает понятную причину. Приложение не придумывает лишнее обучение.
5. Для `JURY_HISTORY_TRAP` выполните `EV_006` через `/api/complete`.
   System Design меняется с 3 до 4, числитель прогресса растёт на 1, блокер
   исчезает. Грейд остаётся Middle: симуляция не является решением о повышении.
6. Повторная загрузка исходных проверочных файлов до выполнения активности не
   дублирует историю. `/api/reset` удаляет проверочные профили и возвращает 200
   исходных сотрудников. Сброс также удаляет остальные изменения в памяти.

Автоматическая проверка этого сценария:

```powershell
BackendAI/.venv/Scripts/python.exe -m pytest BackendAI/tests/test_jury_scenario.py -q
```

## Tests

From the repository root:

```powershell
BackendAI/.venv/Scripts/python.exe -m pytest BackendAI/tests -q
```

Tests exercise the supplied dataset, profile/filter contracts, all employees'
ranking invariants, critical skills versus low skills, negative-history traps,
review-date replay, course ceilings, concurrent completion, upload merges and
rollback, reset, error responses, HR counts and LLM provider failures/timeouts.
Controlled fixtures are used only for edge cases in tests.

Verified locally after the jury-criteria audit: **65 tests pass**, Python 3.13.
The uploaded three-profile scenario covers recommendation and exclusion factors,
course ceilings, idempotent merge, completion, HR changes and reset against the
real catalog. Ranking was compared before/after this audit for all 200 original
employees: selected activities, order and numeric factors are unchanged.
Python 3.12 is the project target but was not available for this local run.
The installed Starlette emits one test-client deprecation warning about httpx.
Provider failures and successes are simulated in automated tests.

Live OpenAI access was verified on 2026-09-23 after the explanation update,
using the saved Windows user environment key and the running API.
`POST /api/recommend` returned fresh `gpt-4o-mini-2024-07-18` explanations for
both `E0001` cards in 2.717 seconds and all three `E0004` cards in 3.151 seconds.
Every card had `explanation_source: "openai"`, `explanation_cached: false`,
and a null fallback reason. `llm_used` was true in both responses.
Repeating `E0004` returned identical generated paragraphs in 0.004 seconds,
with `explanation_cached: true`. The history sentences matched recorded
completions (two, one and zero respectively) without inventing participation.
The previous implementation often hit its four-second deadline; the new
implementation uses concurrent per-card requests and a larger bounded budget.
Live NVIDIA access has not been verified.

## Известные ограничения / Known limitations

The four-factor formula is a transparent heuristic with fixed weights, not a
validated predictor of training success or promotion. Matching history by event
type OR overlapping skill can penalize a different activity of the same broad
format. Counts do not establish reasons for absences, unwillingness to learn,
ability, or workload. Recommendations are voluntary suggestions; no employee
performance scores, leaderboards or compulsory participation incentives exist.

There can be fewer than three recommendations, including none, when requirements
are already covered, sessions/prerequisites block access, course ceilings prevent
useful gains, or history reduces scores to zero. No course is invented to fill
the list. Lead profiles use current-grade requirements, since no higher grade is
defined. Role changes and personal career-goal paths are not modelled. Course
gains are catalog assumptions, not evidence of actual learning; `/api/complete`
is a demonstration of progress calculation, not verified attendance or assessment.

The backend API checks above do not certify the frontend interaction or Docker
deployment against the jury criteria. Those parts were outside this audit's scope.

State is intentionally in memory: use a single server worker. Restart/reset
discards uploads and simulated progress. The API has no authentication; the
frontend role toggle in the source requirements is a presentation convention,
not backend authorization. No database or production identity system is added.
