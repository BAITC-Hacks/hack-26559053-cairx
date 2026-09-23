from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings, settings
from app.core.logging import setup_logging
from app.schemas import (
    CompleteRequest, CompleteResponse, EmployeeProfile, EmployeeSummary, Overview,
    RecommendRequest, RecommendationResponse, UploadResponse,
)
from app.services.completion import complete
from app.services.explain import Explainer
from app.services.loader import DATA_FILES, DataError, DataStore, Dataset
from app.services.profiles import overview, profile, summary
from app.services.scoring import rank

logger = setup_logging()
router = APIRouter()
STATIC_DIR = Path(__file__).resolve().parents[2] / "static"


def get_employee(data: Dataset, employee_id: str):
    employee = data.employees.get(employee_id)
    if employee is None:
        raise HTTPException(404, "Employee not found.")
    return employee


@router.get("/health", tags=["System"])
def health(request: Request):
    data = request.app.state.store.snapshot()
    return {
        "status": "ok", "llm_available": request.app.state.explainer.available,
        "employees_loaded": len(data.employees), "snapshot_date": data.snapshot_date.isoformat(),
    }


@router.get("/employees", response_model=list[EmployeeSummary], tags=["Employees"])
def employees(
    request: Request, search: str = Query("", max_length=200), role: str = "", grade: str = "",
    limit: int = Query(50, ge=1, le=1000),
):
    data = request.app.state.store.snapshot()
    query = search.strip().casefold()
    selected = [employee for employee in data.employees.values()
                if (not query or query in f"{employee.employee_id} {employee.full_name}".casefold())
                and (not role or employee.role.casefold() == role.strip().casefold())
                and (not grade or employee.grade.casefold() == grade.strip().casefold())]
    return [summary(data, employee) for employee in sorted(selected, key=lambda item: item.employee_id)[:limit]]


@router.get("/employees/{employee_id}", response_model=EmployeeProfile, tags=["Employees"])
def employee_profile(employee_id: str, request: Request):
    """Профиль, история завершений и разрывы до следующего грейда.

    Прогресс — покрытие требований к навыкам, а не вероятность повышения.
    В trajectory доступны числитель и знаменатель расчёта; критичные разрывы
    перечислены в blocking_skills. Доступные шаги возвращает /api/recommend.
    """
    data = request.app.state.store.snapshot()
    return profile(data, get_employee(data, employee_id))


async def make_recommendation(request: Request, employee_id: str):
    data = request.app.state.store.snapshot()
    employee = get_employee(data, employee_id)
    recommendations, excluded = await run_in_threadpool(rank, data, employee)
    used = await request.app.state.explainer.explain(data, employee, recommendations)
    return RecommendationResponse(
        employee_id=employee_id, generated_at=datetime.now(timezone.utc), llm_used=used,
        recommendations=recommendations, not_recommended=excluded,
    )


@router.post("/recommend", response_model=RecommendationResponse, tags=["Recommendations"])
async def recommend(payload: RecommendRequest, request: Request):
    """До трёх добровольных шагов с объяснением выбора и альтернатив.

    factors раскрывает разрывы, критичность для целевого грейда, достижимый
    прирост и влияние истории. not_recommended объясняет все остальные
    активности: ограничения, влияние истории или место за пределами топ-3.
    Для оценённых альтернатив доступны factors и сравнение compared_with.
    LLM формулирует текст; при недоступности используется локальное объяснение.
    Пустой список означает, что подходящих шагов в текущем каталоге нет.
    """
    return await make_recommendation(request, payload.employee_id)


@router.post("/recommend/{employee_id}", response_model=RecommendationResponse, tags=["Recommendations"])
async def recommend_by_id(employee_id: str, request: Request):
    return await make_recommendation(request, employee_id)


async def finish_activity(request: Request, employee_id: str, event_id: str):
    data, result = await run_in_threadpool(complete, request.app.state.store, employee_id, event_id)
    result.llm_used = await request.app.state.explainer.explain(
        data, data.employees[employee_id], result.new_recommendations,
    )
    return result


@router.post("/complete", response_model=CompleteResponse, tags=["Recommendations"])
async def complete_activity(payload: CompleteRequest, request: Request):
    """Симулировать завершение добровольной активности и пересчитать прогресс.

    Возвращает уровни before/after, предыдущую и новую траекторию и новые шаги.
    Обязательные активности исключены из симуляции. Повторное завершение
    отклоняется, кроме повторяемого клуба в другую дату среза. Грейд автоматически
    не меняется; действие не подтверждает фактическое прохождение обучения.
    """
    return await finish_activity(request, payload.employee_id, payload.event_id)


@router.post("/complete/{employee_id}/{event_id}", response_model=CompleteResponse, tags=["Recommendations"])
async def complete_by_id(employee_id: str, event_id: str, request: Request):
    return await finish_activity(request, employee_id, event_id)


@router.get("/hr/overview", response_model=Overview, tags=["HR"])
def hr_overview(request: Request):
    """Дефициты навыков, сотрудники без доступного шага и участие по активностям.

    Дефициты сравниваются с требованиями целевого грейда каждой роли.
    Список сотрудников без шага сопровождается причинами и не является
    рейтингом результативности. Участие отражает записи загруженной истории.
    """
    return overview(request.app.state.store.snapshot())


@router.post("/upload", response_model=UploadResponse, tags=["Data"])
async def upload(
    request: Request, files: list[UploadFile] | None = File(None),
    bracket_files: list[UploadFile] | None = File(None, alias="files[]"),
):
    """Добавить или обновить профили и историю, сохранив остальные данные.

    Принимает любое подмножество employees.json, activity_history.csv,
    skills.json и events.json в формате датасета. Можно загрузить три профиля
    жюри вместе с их историей одним запросом. Ошибка в любом файле отменяет
    весь пакет. Изменения хранятся в памяти до перезапуска или /api/reset.
    """
    uploads = (files or []) + (bracket_files or [])
    try:
        if not uploads or len(uploads) > len(DATA_FILES):
            raise HTTPException(422, "Upload between one and four supported dataset files.")
        batch, total = {}, 0
        maximum = request.app.state.settings.MAX_UPLOAD_BYTES
        for item in uploads:
            if item.filename not in DATA_FILES:
                raise HTTPException(422, f"Unsupported filename. Expected: {', '.join(DATA_FILES)}.")
            if item.filename in batch:
                raise HTTPException(422, f"Duplicate upload filename: {item.filename}.")
            content = await item.read(maximum - total + 1)
            total += len(content)
            if total > maximum:
                raise HTTPException(413, f"Total uploaded data exceeds {maximum} bytes.")
            batch[item.filename] = content
        return await run_in_threadpool(request.app.state.store.merge, batch)
    finally:
        for item in uploads:
            await item.close()


@router.post("/reset", tags=["Data"])
def reset(request: Request):
    data = request.app.state.store.reset()
    return {
        "status": "ok", "employees_loaded": len(data.employees),
        "loaded": {"employees": len(data.employees), "events": len(data.events),
                   "skills": len(data.skills), "history_rows": len(data.history)},
    }


def create_app(config: Settings | None = None) -> FastAPI:
    config = config or settings

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        store = DataStore(config.data_path, config.SNAPSHOT_DATE)
        data = await run_in_threadpool(store.reset)
        application.state.store = store
        application.state.explainer = Explainer(config)
        logger.info("Career Quest loaded %d employees and %d activities", len(data.employees), len(data.events))
        try:
            yield
        finally:
            await application.state.explainer.close()

    application = FastAPI(
        title=config.PROJECT_NAME, version=config.VERSION, description=config.DESCRIPTION,
        openapi_url=f"{config.API_V1_STR}/openapi.json", lifespan=lifespan,
    )
    application.state.settings = config
    application.add_middleware(
        CORSMiddleware, allow_origins=config.CORS_ORIGINS,
        allow_credentials="*" not in config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"],
    )

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={
            "success": False, "error_code": "VALIDATION_ERROR", "detail": "Invalid request data.",
            "errors": [{"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
                       for error in exc.errors()],
        })

    @application.exception_handler(DataError)
    async def dataset_error(request: Request, exc: DataError):
        return JSONResponse(status_code=422, content={
            "success": False, "error_code": "INVALID_DATASET", "detail": str(exc),
        })

    @application.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, headers=exc.headers, content={
            "success": False, "error_code": f"HTTP_{exc.status_code}", "detail": exc.detail,
        })

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.error("Unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path)
        return JSONResponse(status_code=500, content={
            "success": False, "error_code": "INTERNAL_SERVER_ERROR",
            "detail": "An internal server error occurred.",
        })

    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @application.get("/", include_in_schema=False)
    def root():
        return FileResponse(STATIC_DIR / "index.html")

    application.include_router(router, prefix="/api")
    # Retain the configured version prefix for existing backend clients and health checks.
    if config.API_V1_STR != "/api":
        application.include_router(router, prefix=config.API_V1_STR, include_in_schema=False)
    return application


app = create_app()
