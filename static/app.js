const USE_MOCK = true;

async function api(path, options = {}) {
  try {
    if (USE_MOCK) {
      await new Promise((resolve) => setTimeout(resolve, 300 + Math.floor(Math.random() * 301)));
      return await window.CareerQuestMock.handle(path, options);
    }
    const response = await fetch(path, options);
    const contentType = response.headers.get("content-type") || "";
    const body = contentType.includes("application/json") ? await response.json() : await response.text();
    if (!response.ok) {
      const detail = body && typeof body === "object" ? (body.detail ?? body.message ?? body.error) : body;
      const message = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((item) => item.msg || item.message || JSON.stringify(item)).join("; ") : `Ошибка сервера (${response.status}).`;
      throw new Error(message || `Ошибка сервера (${response.status}).`);
    }
    return body;
  } catch (error) {
    if (error instanceof TypeError) throw new Error("Не удалось связаться с сервером. Проверьте подключение и повторите попытку.");
    if (error instanceof SyntaxError) throw new Error("Сервер вернул некорректный ответ. Повторите попытку.");
    throw error;
  }
}

(() => {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const state = {
    role:"employee", tab:"employee", employees:[], selectedId:null,
    profile:null, recommendations:null, showAllSkills:false,
    selectionVersion:0, hrLoaded:false, uploadResult:null, selectedFiles:[],
  };
  const labels = {
    workshop:"Воркшоп", course:"Курс", compliance:"Обязательная программа",
    mentoring:"Менторство", onboarding:"Онбординг", certification:"Сертификация", meetup:"Встреча",
    completed:"Завершено", no_show:"Пропущено", dropped:"Прервано",
    declined:"Отказ", overdue:"Просрочено", in_progress:"В процессе",
    online:"Онлайн", offline:"Офлайн", hybrid:"Гибридный", office:"Офис", remote:"Удалённо",
  };
  const statusKeys = ["completed", "no_show", "dropped", "declined", "overdue", "in_progress"];
  const circleLength = 2 * Math.PI * 52;
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" })[char]);
  const number = (value, digits = 0) => Number.isFinite(Number(value)) ? new Intl.NumberFormat("ru-RU", { maximumFractionDigits:digits }).format(Number(value)) : "—";
  const clamp = (value, min, max) => Math.min(max, Math.max(min, Number(value) || 0));
  const show = (element, visible) => { element.hidden = !visible; };
  const text = (value, fallback = "—") => value === null || value === undefined || value === "" ? fallback : String(value);
  const skillWord = (count) => count % 10 === 1 && count % 100 !== 11 ? "навык" : [2, 3, 4].includes(count % 10) && ![12, 13, 14].includes(count % 100) ? "навыка" : "навыков";
  const criticalSkillPhrase = (count) => `${count} ${count === 1 ? "критичный" : "критичных"} ${skillWord(count)}`;
  const date = (value) => {
    if (!value) return "Дата не указана";
    const parsed = new Date(`${value}T12:00:00`);
    return Number.isNaN(parsed.getTime()) ? String(value) : new Intl.DateTimeFormat("ru-RU", { day:"numeric", month:"long", year:"numeric" }).format(parsed);
  };

  function icon(name, className = "w-5 h-5") {
    const paths = {
      arrow:'<path d="M5 12h14m-6-6 6 6-6 6"/>',
      check:'<path d="m5 12 4 4L19 6"/>',
      close:'<path d="M6 6l12 12M18 6 6 18"/>',
      alert:'<path d="M12 3 2 21h20L12 3Zm0 6v5m0 3h.01"/>',
      clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
      calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 10h18"/>',
      shield:'<path d="M12 2 4 5v6c0 5 3.3 8.5 8 11 4.7-2.5 8-6 8-11V5l-8-3Z"/><path d="m9 12 2 2 4-4"/>',
      target:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
      chevron:'<path d="m6 9 6 6 6-6"/>',
      file:'<path d="M5 2h9l5 5v15H5V2Z"/><path d="M14 2v5h5M8 12h8m-8 4h8"/>',
      spark:'<path d="m12 2 1.7 6.3L20 10l-6.3 1.7L12 18l-1.7-6.3L4 10l6.3-1.7L12 2Zm7 13 .7 2.3L22 18l-2.3.7L19 21l-.7-2.3L16 18l2.3-.7L19 15Z"/>',
      search:'<circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 4.2 4.2"/>',
      play:'<path d="m8 5 11 7-11 7V5Z"/>',
      minus:'<path d="M5 12h14"/>',
    };
    return `<svg class="${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.target}</svg>`;
  }

  function skeleton(kind) {
    if (kind === "profile") return `<div class="card p-8 h-[258px]"><div class="flex justify-between"><div class="space-y-4 w-2/3"><div class="skeleton h-4 w-28"></div><div class="skeleton h-9 w-3/4"></div><div class="skeleton h-4 w-1/2"></div><div class="skeleton h-3 w-full mt-8"></div></div><div class="skeleton h-36 w-36 rounded-full"></div></div></div>`;
    if (kind === "quests") return [0, 1, 2].map(() => `<div class="card p-6 h-[315px] space-y-5"><div class="skeleton h-3 w-20"></div><div class="skeleton h-7 w-4/5"></div><div class="skeleton h-3 w-2/3"></div><div class="skeleton h-16 w-full"></div><div class="skeleton h-10 w-1/2"></div></div>`).join("");
    if (kind === "skills") return `<div class="card p-6 grid grid-cols-2 gap-8">${[0, 1, 2, 3].map(() => '<div class="space-y-4"><div class="skeleton h-5 w-1/2"></div><div class="skeleton h-3 w-full"></div></div>').join("")}</div>`;
    return `<div class="card p-6 space-y-5">${[0, 1, 2].map(() => '<div class="skeleton h-12 w-full"></div>').join("")}</div>`;
  }

  function errorCard(message, action, title = "Не удалось загрузить данные") {
    return `<div class="card p-6 flex items-center justify-between gap-6 border-l-4 border-l-[#C46B37]" role="alert"><div class="flex items-start gap-3"><span class="text-[#C46B37] shrink-0">${icon("alert")}</span><div><h3 class="font-extrabold text-sm">${esc(title)}</h3><p class="mt-1 text-xs text-ink-500 leading-5">${esc(message)}</p></div></div><button type="button" class="button-secondary shrink-0" data-retry="${esc(action)}">Повторить</button></div>`;
  }

  function emptyCard(title, description) {
    return `<div class="card p-8 text-center"><span class="inline-grid place-items-center w-11 h-11 rounded-xl bg-halyk-50 text-halyk-700">${icon("target")}</span><h3 class="mt-3 text-base font-extrabold">${esc(title)}</h3><p class="mt-1 text-xs text-ink-500">${esc(description)}</p></div>`;
  }

  function setTab(tab) {
    if (tab === "hr" && state.role !== "hr") return;
    state.tab = tab;
    ["employee", "hr", "data"].forEach((name) => show($(`#${name}-panel`), name === tab));
    document.querySelectorAll(".nav-tab").forEach((button) => {
      const active = button.dataset.tab === tab;
      button.classList.toggle("active", active);
      if (active) button.setAttribute("aria-current", "page"); else button.removeAttribute("aria-current");
    });
    if (tab === "hr" && !state.hrLoaded) loadHr();
  }

  function setRole(role) {
    state.role = role;
    show($("#hr-tab"), role === "hr");
    if (role === "employee" && state.tab === "hr") setTab("employee");
  }

  async function loadEmployees() {
    $("#employee-search").disabled = true;
    $("#employee-list-status").innerHTML = '<span class="skeleton inline-block h-3 w-32 align-middle" aria-label="Загружаем сотрудников"></span>';
    $("#employee-list-error").innerHTML = "";
    try {
      const result = await api("/api/employees");
      if (!Array.isArray(result)) throw new Error("Сервер вернул неверный формат списка сотрудников.");
      state.employees = result;
      $("#employee-search").disabled = false;
      $("#employee-list-status").textContent = result.length ? `${result.length} профилей доступно` : "Сотрудников пока нет. Загрузите данные во вкладке «Данные».";
      renderOptions();
    } catch (error) {
      state.employees = [];
      $("#employee-search").disabled = false;
      $("#employee-list-status").textContent = "Список недоступен";
      $("#employee-list-error").innerHTML = errorCard(error.message, "employees", "Не удалось получить сотрудников");
    }
  }

  function renderOptions() {
    const query = $("#employee-search").value.trim().toLocaleLowerCase("ru");
    const matches = state.employees.filter((employee) => String(employee.full_name || "").toLocaleLowerCase("ru").includes(query));
    $("#employee-options").innerHTML = matches.length ? matches.map((employee) => `<button type="button" class="selector-option" role="option" data-employee-id="${esc(employee.employee_id)}"><span><span class="block text-sm font-extrabold text-ink-900">${esc(employee.full_name)}</span><span class="block mt-1 text-[11px] text-ink-500">${esc(employee.role)} · ${esc(employee.grade)}</span></span>${employee.has_recommendation === false ? '<span class="text-[10px] font-bold text-ink-500">Без рекомендаций</span>' : icon("arrow", "w-4 h-4 text-halyk-600")}</button>`).join("") : '<p class="p-4 text-xs text-ink-500">По вашему запросу сотрудники не найдены.</p>';
  }

  function openOptions() { renderOptions(); show($("#employee-options"), true); $("#employee-search").setAttribute("aria-expanded", "true"); }
  function closeOptions() { show($("#employee-options"), false); $("#employee-search").setAttribute("aria-expanded", "false"); }

  async function selectEmployee(id) {
    const version = ++state.selectionVersion;
    state.selectedId = String(id);
    state.profile = null;
    state.recommendations = null;
    state.showAllSkills = false;
    const summary = state.employees.find((employee) => String(employee.employee_id) === String(id));
    $("#employee-search").value = summary?.full_name || String(id);
    closeOptions();
    setTab("employee");
    show($("#employee-empty"), false);
    show($("#employee-content"), true);
    $("#profile-mount").innerHTML = skeleton("profile");
    $("#recommend-mount").innerHTML = skeleton("quests");
    $("#skills-mount").innerHTML = skeleton("skills");
    $("#history-mount").innerHTML = skeleton("history");
    show($("#not-recommended"), false);
    show($("#llm-note"), false);
    await Promise.all([loadProfile(version), loadRecommendations(version)]);
  }

  async function loadProfile(version = state.selectionVersion) {
    $("#profile-mount").innerHTML = skeleton("profile");
    $("#skills-mount").innerHTML = skeleton("skills");
    $("#history-mount").innerHTML = skeleton("history");
    try {
      const profile = await api(`/api/employees/${encodeURIComponent(state.selectedId)}`);
      if (version !== state.selectionVersion) return;
      state.profile = profile;
      renderProfile(); renderSkills(); renderHistory();
    } catch (error) {
      if (version !== state.selectionVersion) return;
      $("#profile-mount").innerHTML = errorCard(error.message, "profile", "Профиль недоступен");
      $("#skills-mount").innerHTML = emptyCard("Навыки пока недоступны", "Повторите загрузку профиля.");
      $("#history-mount").innerHTML = emptyCard("История пока недоступна", "Повторите загрузку профиля.");
    }
  }

  async function loadRecommendations(version = state.selectionVersion) {
    $("#recommend-mount").innerHTML = skeleton("quests");
    try {
      const result = await api("/api/recommend", { method:"POST", headers:{ "Content-Type":"application/json" }, body:JSON.stringify({ employee_id:state.selectedId }) });
      if (version !== state.selectionVersion) return;
      state.recommendations = result;
      renderRecommendations();
    } catch (error) {
      if (version !== state.selectionVersion) return;
      $("#recommend-mount").innerHTML = `<div class="col-span-3">${errorCard(error.message, "recommend", "Рекомендации недоступны")}</div>`;
      show($("#not-recommended"), false);
    }
  }

  function gradeLevel(grade) { const level = ["Junior", "Middle", "Senior", "Lead", "Principal"].indexOf(grade); return level < 0 ? "—" : String(level + 1); }
  function progressRatio(trajectory) {
    const raw = Number(trajectory?.progress_to_next_grade) || 0;
    return clamp(raw > 1 ? raw / 100 : raw, 0, 1);
  }

  function renderProfile(fromProgress = null) {
    const profile = state.profile;
    if (!profile) return;
    const progress = progressRatio(profile.trajectory);
    const initial = fromProgress === null ? progress : clamp(fromProgress, 0, 1);
    const criticalCount = (profile.skills || []).filter((skill) => skill.critical && Number(skill.gap) > 0).length;
    const initials = String(profile.full_name || "?").trim().split(/\s+/).slice(0, 2).map((piece) => piece[0]).join("").toUpperCase();
    $("#profile-mount").innerHTML = `<section class="rounded-2xl bg-gradient-to-r from-halyk-700 to-halyk-500 text-white p-8 shadow-card" aria-label="Профиль сотрудника"><div class="flex items-start justify-between gap-8"><div class="flex-1 min-w-0"><div class="flex items-start gap-5"><div class="w-14 h-14 shrink-0 grid place-items-center rounded-2xl bg-white/15 border border-white/25 text-lg font-extrabold">${esc(initials)}</div><div><p class="text-[11px] uppercase tracking-[.17em] font-extrabold text-white/70">Маршрут развития</p><h2 class="text-[30px] leading-tight font-extrabold tracking-[-.05em] mt-1">${esc(profile.full_name)}</h2><p class="text-sm text-white/80 mt-1">${esc(profile.role)} · ${esc(profile.department)}</p></div></div><div class="mt-8 flex items-center gap-3"><span class="px-3 py-1.5 rounded-lg bg-white/15 text-xs font-extrabold">${esc(profile.grade)} → ${esc(profile.next_grade)}</span><span class="text-xs text-white/75">${esc(profile.tenure_months)} мес. в компании</span><span class="text-xs text-white/75">${esc(labels[profile.work_format] || profile.work_format)}</span></div><div class="mt-7 max-w-[565px]"><div class="flex justify-between gap-3 text-xs font-bold mb-2"><span>Прогресс к ${esc(profile.next_grade)}</span><span class="xp-percent">${number(progress * 100)}%</span></div><div class="w-full h-2 rounded-full bg-white/25 overflow-hidden"><div class="xp-fill h-full rounded-full bg-white" style="width:${initial * 100}%"></div></div><p class="mt-2 text-[11px] text-white/75">${criticalCount ? `До ${esc(profile.next_grade)} осталось закрыть ${criticalSkillPhrase(criticalCount)}` : `Критичные навыки для ${esc(profile.next_grade)} закрыты`}</p></div></div><div class="relative w-40 h-40 shrink-0" role="progressbar" aria-label="Прогресс к следующему грейду" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(progress * 100)}"><svg class="w-40 h-40 -rotate-90" viewBox="0 0 128 128" aria-hidden="true"><circle cx="64" cy="64" r="52" stroke="rgba(255,255,255,.24)" stroke-width="9" fill="none"/><circle class="ring-progress" cx="64" cy="64" r="52" stroke="white" stroke-linecap="round" stroke-width="9" fill="none" stroke-dasharray="${circleLength}" stroke-dashoffset="${circleLength * (1 - initial)}"/></svg><div class="absolute inset-0 flex flex-col items-center justify-center"><span class="text-[10px] font-extrabold uppercase tracking-widest text-white/70">Уровень</span><span class="text-5xl leading-none font-extrabold mt-1">${gradeLevel(profile.grade)}</span><span class="text-[10px] text-white/75 mt-1">${esc(profile.grade)}</span></div></div></div></section>`;
    if (fromProgress !== null) requestAnimationFrame(() => requestAnimationFrame(() => {
      const ring = $("#profile-mount .ring-progress");
      const xp = $("#profile-mount .xp-fill");
      if (ring) ring.style.strokeDashoffset = String(circleLength * (1 - progress));
      if (xp) xp.style.width = `${progress * 100}%`;
    }));
  }

  function prettyKey(key) { return String(key).replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
  function factorText(value) {
    if (Array.isArray(value)) return value.map(factorText).join(", ");
    if (value && typeof value === "object") return Object.entries(value).map(([key, item]) => `${prettyKey(key)} ${factorText(item)}`).join(" · ");
    if (typeof value === "boolean") return value ? "да" : "нет";
    return text(value);
  }

  function renderRecommendations() {
    const result = state.recommendations;
    if (!result) return;
    show($("#llm-note"), result.llm_used === false);
    const items = Array.isArray(result.recommendations) ? result.recommendations.slice(0, 3) : [];
    $("#recommend-mount").innerHTML = items.length ? items.map((item, index) => {
      const factors = item.factors && typeof item.factors === "object" ? Object.entries(item.factors) : [];
      const nearest = Array.isArray(item.upcoming_sessions) && item.upcoming_sessions.length ? date(item.upcoming_sessions[0]) : "Дата уточняется";
      return `<article class="quest-card flex flex-col"><div class="flex justify-between items-start gap-3"><span class="text-[10px] font-extrabold uppercase tracking-[.16em] text-halyk-600">Квест ${String(index + 1).padStart(2, "0")}</span><span class="w-8 h-8 grid place-items-center rounded-lg bg-halyk-50 text-halyk-700">${icon("spark", "w-4 h-4")}</span></div><h3 class="mt-4 text-lg leading-6 tracking-tight font-extrabold">${esc(item.title)}</h3><div class="flex flex-wrap items-center gap-x-3 gap-y-2 mt-3 text-[11px] font-bold text-ink-500"><span>${esc(labels[item.type] || prettyKey(item.type))}</span><span class="w-1 h-1 rounded-full bg-ink-300"></span><span>${esc(number(item.duration_hours))} ч.</span><span class="w-1 h-1 rounded-full bg-ink-300"></span><span>${esc(nearest)}</span></div><p class="mt-5 text-xs leading-6 text-ink-700 flex-1">${esc(item.explanation || "Объяснение для активности пока не предоставлено.")}</p><div class="mt-5 pt-5 border-t border-surface-line"><p class="text-[10px] font-extrabold uppercase tracking-widest text-ink-500 mb-2">Почему подходит</p><div class="flex flex-wrap gap-1.5">${factors.length ? factors.map(([key, value]) => `<span class="factor-pill" title="${esc(factorText(value))}">${esc(prettyKey(key))}: ${esc(factorText(value))}</span>`).join("") : '<span class="text-xs text-ink-500">Факторы не переданы.</span>'}</div></div><button class="button-primary mt-6 w-full complete-button" type="button" data-event-id="${esc(item.event_id)}">${icon("play", "w-4 h-4")} Пройти</button></article>`;
    }).join("") : `<div class="col-span-3">${emptyCard("Нет рекомендаций", "Для текущих навыков и доступных активностей подходящий следующий шаг не найден.")}</div>`;
    const excluded = Array.isArray(result.not_recommended) ? result.not_recommended : [];
    show($("#not-recommended"), excluded.length > 0);
    $("#not-recommended-count").textContent = excluded.length ? `${excluded.length} активности` : "";
    $("#not-recommended-mount").innerHTML = excluded.map((item) => `<div class="border-t border-surface-line pt-4 pb-1"><p class="text-sm font-extrabold">${esc(item.title)}</p><p class="text-xs leading-5 text-ink-500 mt-1">${esc(item.reason || "Причина не указана.")}</p></div>`).join("");
  }

  function skillCard(skill, starts) {
    const current = starts.has(String(skill.skill_id)) ? starts.get(String(skill.skill_id)) : Number(skill.current);
    const required = clamp(skill.required_next, 0, 5);
    const gap = Number(skill.gap) > 0;
    return `<article class="rounded-xl border ${gap ? "border-halyk-200 bg-halyk-50/30" : "border-surface-line bg-white"} p-5" data-skill-id="${esc(skill.skill_id)}"><div class="flex items-start justify-between gap-3"><div class="flex items-center gap-2 min-w-0"><h3 class="text-sm font-extrabold truncate">${esc(skill.name)}</h3>${skill.critical ? `<span class="text-halyk-700" title="Критичный навык" aria-label="Критичный навык">${icon("shield", "w-4 h-4")}</span>` : ""}</div><span class="text-[11px] font-extrabold ${gap ? "text-halyk-700" : "text-ink-500"}">${gap ? `Разрыв ${number(skill.gap)}` : "Цель закрыта"}</span></div><p class="mt-1 text-[10px] uppercase tracking-wider font-bold text-ink-500">${esc(skill.category)} · ${esc(skill.type)}</p><div class="skill-meter mt-6">${[1, 2, 3, 4, 5].map((level) => `<span class="segment ${level <= current ? "filled" : ""}" data-level="${level}"></span>`).join("")}<span class="skill-marker" style="left:${required * 20}%" title="Требуемый уровень ${required}" aria-hidden="true"></span></div><div class="flex justify-between text-[11px] text-ink-500 mt-3"><span>Сейчас <strong class="text-ink-900">${number(skill.current)}/5</strong></span><span>Нужно <strong class="text-ink-900">${number(skill.required_next)}/5</strong></span></div></article>`;
  }

  function renderSkills(updates = []) {
    const skills = Array.isArray(state.profile?.skills) ? state.profile.skills : [];
    if (!skills.length) { $("#skills-mount").innerHTML = emptyCard("Навыки не указаны", "Загрузите данные о навыках сотрудника."); return; }
    const gaps = skills.filter((skill) => Number(skill.gap) > 0);
    const others = skills.filter((skill) => Number(skill.gap) <= 0);
    const visible = state.showAllSkills ? [...gaps, ...others] : gaps;
    const starts = new Map(updates.map((item) => [String(item.skill_id), Number(item.before)]));
    $("#skills-mount").innerHTML = `<div class="card p-6"><div class="flex items-center justify-between mb-5"><div><span class="text-sm font-extrabold">${gaps.length} навыка с разрывом</span><p class="text-xs text-ink-500 mt-1">Пять сегментов — уровни 1–5. Риска показывает цель следующего грейда.</p></div><span class="flex items-center gap-2 text-[11px] text-ink-500"><span class="w-3 h-3 rounded-sm bg-halyk-600"></span>Текущий уровень <span class="w-[2px] h-4 bg-ink-900 ml-3"></span> Требуется</span></div>${visible.length ? `<div class="grid grid-cols-2 gap-4">${visible.map((skill) => skillCard(skill, starts)).join("")}</div>` : '<p class="text-sm text-ink-500">Разрывов по навыкам нет. Все требуемые уровни достигнуты.</p>'}${others.length ? `<button id="toggle-skills" class="button-secondary mt-5" type="button">${state.showAllSkills ? "Скрыть навыки без разрыва" : `Показать все навыки (${skills.length})`}${icon("chevron", "w-4 h-4")}</button>` : ""}</div>`;
    if (updates.length) requestAnimationFrame(() => requestAnimationFrame(() => {
      updates.forEach((update) => {
        const row = [...document.querySelectorAll("[data-skill-id]")].find((item) => item.dataset.skillId === String(update.skill_id));
        if (!row) return;
        row.querySelectorAll(".segment").forEach((segment) => {
          const newLevel = Number(segment.dataset.level) <= Number(update.after);
          segment.classList.toggle("filled", newLevel);
          if (newLevel && Number(segment.dataset.level) > Number(update.before)) segment.classList.add("newly-filled");
        });
      });
    }));
  }

  function renderHistory() {
    const profile = state.profile;
    if (!profile) return;
    const stats = profile.history_stats || {};
    const history = Array.isArray(profile.completed_activities) ? profile.completed_activities : [];
    $("#history-mount").innerHTML = `<div class="card p-6"><div class="grid grid-cols-6 gap-3 mb-6">${statusKeys.map((key) => `<div class="rounded-xl bg-surface-muted px-3 py-3"><span class="status-icon status-${key} mb-2">${icon(key === "completed" ? "check" : key === "in_progress" ? "play" : key === "no_show" ? "minus" : key === "overdue" ? "clock" : "close", "w-4 h-4")}</span><strong class="block text-lg font-extrabold">${number(stats[key] ?? 0)}</strong><span class="text-[10px] font-semibold text-ink-500">${esc(labels[key])}</span></div>`).join("")}</div>${history.length ? `<div class="divide-y divide-surface-line">${history.map((item) => { const status = statusKeys.includes(item.status) ? item.status : "completed"; const gained = Array.isArray(item.skills_gained) ? item.skills_gained : []; return `<div class="flex items-center gap-4 py-3"><span class="status-icon status-${status}">${icon(status === "completed" ? "check" : status === "in_progress" ? "play" : status === "no_show" ? "minus" : status === "overdue" ? "clock" : "close", "w-4 h-4")}</span><div class="flex-1 min-w-0"><p class="text-xs font-extrabold truncate">${esc(item.title)}</p><p class="text-[11px] text-ink-500 mt-1">${esc(date(item.date))}${gained.length ? ` · ${gained.map((gain) => `+${number(gain.gain)} ${esc(gain.name)}`).join(", ")}` : ""}</p></div><span class="text-[10px] font-extrabold status-${status} px-2.5 py-1 rounded-lg">${esc(labels[status])}</span></div>`; }).join("")}</div>` : '<p class="text-xs text-ink-500">История активностей пока пуста. Счётчики выше обновятся после первых действий.</p>'}</div>`;
  }

  function toast(message) {
    const node = document.createElement("div");
    node.className = "toast-item flex items-center gap-3 rounded-xl bg-ink-900 text-white px-5 py-4 shadow-xl text-sm font-extrabold";
    node.innerHTML = `${icon("check", "w-5 h-5 text-halyk-200")}<span>${esc(message)}</span>`;
    $("#toast-region").append(node);
    window.setTimeout(() => node.remove(), 4200);
  }

  async function completeActivity(eventId, button) {
    const employeeId = state.selectedId;
    const version = state.selectionVersion;
    if (!state.profile) { $("#profile-mount").innerHTML = errorCard("Дождитесь загрузки профиля и повторите попытку.", "profile", "Нужен профиль сотрудника"); return; }
    button.disabled = true;
    button.textContent = "Сохраняем…";
    try {
      const result = await api("/api/complete", { method:"POST", headers:{ "Content-Type":"application/json" }, body:JSON.stringify({ employee_id:employeeId, event_id:eventId }) });
      if (version !== state.selectionVersion) return;
      const updates = Array.isArray(result.updated_skills) ? result.updated_skills : [];
      const beforeProgress = progressRatio(state.profile.trajectory);
      state.profile.skills = (state.profile.skills || []).map((skill) => {
        const update = updates.find((item) => String(item.skill_id) === String(skill.skill_id));
        return update ? { ...skill, current:update.after, gap:Math.max(0, Number(skill.required_next) - Number(update.after)) } : skill;
      });
      if (result.trajectory) state.profile.trajectory = result.trajectory;
      state.showAllSkills = true;
      state.recommendations = { llm_used:result.new_recommendations?.llm_used, recommendations:Array.isArray(result.new_recommendations) ? result.new_recommendations : result.new_recommendations?.recommendations || [], not_recommended:result.new_recommendations?.not_recommended || [] };
      renderProfile(beforeProgress);
      renderSkills(updates);
      renderRecommendations();
      const gains = updates.filter((item) => Number(item.after) > Number(item.before)).map((item) => `+${number(Number(item.after) - Number(item.before))} ${item.name || state.profile.skills.find((skill) => skill.skill_id === item.skill_id)?.name || item.skill_id}`);
      toast(gains.length ? gains.join(" · ") : "Активность выполнена");
      window.setTimeout(async () => {
        if (version !== state.selectionVersion) return;
        try {
          const fresh = await api(`/api/employees/${encodeURIComponent(employeeId)}`);
          if (version !== state.selectionVersion) return;
          state.profile = fresh;
          renderProfile(); renderSkills(); renderHistory();
        } catch (error) {
          $("#history-mount").innerHTML = errorCard(`Активность сохранена, но история не обновилась: ${error.message}`, "history", "История недоступна");
        }
      }, 650);
    } catch (error) {
      button.disabled = false;
      button.innerHTML = `${icon("play", "w-4 h-4")} Пройти`;
      $("#recommend-mount").insertAdjacentHTML("afterbegin", `<div class="col-span-3">${errorCard(error.message, "recommend", "Не удалось завершить активность")}</div>`);
    }
  }

  function table(headers, rows, emptyMessage) {
    if (!rows.length) return `<p class="text-xs text-ink-500 px-6 pb-6">${esc(emptyMessage)}</p>`;
    return `<table class="table-zebra w-full"><thead><tr>${headers.map((item) => `<th>${esc(item)}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table>`;
  }

  async function loadHr() {
    state.hrLoaded = false;
    $("#hr-mount").innerHTML = `<div class="grid grid-cols-3 gap-5 mb-8">${[0, 1, 2].map(() => '<div class="card p-6"><div class="skeleton h-4 w-28"></div><div class="skeleton h-10 w-20 mt-5"></div></div>').join("")}</div>${skeleton("table")}`;
    try {
      const data = await api("/api/hr/overview");
      if (state.role !== "hr") return;
      const totals = data.totals || {};
      const weak = Array.isArray(data.weakest_skills) ? data.weakest_skills : [];
      const without = Array.isArray(data.no_recommendation) ? data.no_recommendation : [];
      const participation = Array.isArray(data.activity_participation) ? data.activity_participation : [];
      $("#hr-mount").innerHTML = `<div class="grid grid-cols-3 gap-5 mb-8">${[["Сотрудников", totals.employees], ["С разрывами", totals.with_gaps], ["Без рекомендации", totals.no_recommendation]].map(([label, value]) => `<div class="card p-6"><p class="eyebrow">${esc(label)}</p><strong class="block text-4xl font-extrabold tracking-tight mt-4">${number(value ?? 0)}</strong></div>`).join("")}</div><div class="space-y-8"><section class="card overflow-hidden"><div class="px-6 pt-6 pb-4"><h2 class="section-title">Проседающие навыки</h2><p class="text-xs text-ink-500 mt-1">Средний уровень команды относительно нужного.</p></div>${table(["Навык", "Средний уровень", "Нужно", "Ниже цели"], weak.map((item) => `<tr><td class="font-extrabold">${esc(item.name)}</td><td>${number(item.avg_level, 1)}</td><td>${number(item.required_avg, 1)}</td><td>${number(item.employees_below)}</td></tr>`), "Навыков с разрывом сейчас нет.")}</section><section class="card overflow-hidden"><div class="px-6 pt-6 pb-4"><h2 class="section-title">Без рекомендации</h2><p class="text-xs text-ink-500 mt-1">Кому пока не нашёлся подходящий следующий шаг.</p></div>${table(["Сотрудник", "Роль", "Причина"], without.map((item) => `<tr><td><button type="button" class="text-halyk-700 font-extrabold hover:underline hr-person" data-employee-id="${esc(item.employee_id)}">${esc(item.full_name)}</button></td><td>${esc(item.role)}</td><td>${esc(item.reason)}</td></tr>`), "Сотрудников без рекомендации нет.")}</section><section class="card overflow-hidden"><div class="px-6 pt-6 pb-4"><h2 class="section-title">Участие по активностям</h2><p class="text-xs text-ink-500 mt-1">Сводная картина прохождения без оценки отдельных сотрудников.</p></div>${table(["Активность", "Завершено", "Пропуск", "Прервано", "Отказ", "Участие"], participation.map((item) => `<tr><td class="font-extrabold">${esc(item.title)}</td><td>${number(item.completed)}</td><td>${number(item.no_show)}</td><td>${number(item.dropped)}</td><td>${number(item.declined)}</td><td class="font-extrabold text-halyk-700">${number(Number(item.rate) <= 1 ? Number(item.rate) * 100 : item.rate)}%</td></tr>`), "Данных об участии пока нет.")}</section></div>`;
      state.hrLoaded = true;
    } catch (error) {
      $("#hr-mount").innerHTML = errorCard(error.message, "hr", "Обзор HR недоступен");
    }
  }

  function renderSelectedFiles() {
    const files = state.selectedFiles;
    $("#selected-files").innerHTML = files.length ? `<div class="space-y-2">${files.map((file) => `<div class="flex items-center gap-2 rounded-lg bg-surface-muted px-3 py-2 text-xs font-bold text-ink-700">${icon("file", "w-4 h-4 text-halyk-700")}<span>${esc(file.name)}</span><span class="ml-auto text-ink-500 font-medium">${number(file.size / 1024, 1)} КБ</span></div>`).join("")}</div>` : "Файлы пока не выбраны.";
  }

  function renderUploadResult(result) {
    const loaded = result.loaded || {};
    const ids = Array.isArray(result.employee_ids) ? result.employee_ids : [];
    const warnings = Array.isArray(result.warnings) ? result.warnings : [];
    $("#data-mount").innerHTML = `<section class="card p-6"><div class="flex items-center gap-3 mb-5"><span class="w-9 h-9 grid place-items-center rounded-lg bg-halyk-50 text-halyk-700">${icon("check")}</span><div><h2 class="text-lg font-extrabold">Загрузка завершена</h2><p class="text-xs text-ink-500">Проверьте загруженные записи и откройте профиль.</p></div></div><div class="grid grid-cols-3 gap-4">${[["Сотрудники", loaded.employees], ["Активности", loaded.events], ["Строки истории", loaded.history_rows]].map(([label, value]) => `<div class="rounded-xl bg-surface-muted p-4"><strong class="text-2xl font-extrabold">${number(value ?? 0)}</strong><p class="text-[11px] text-ink-500 mt-1">${esc(label)}</p></div>`).join("")}</div><h3 class="text-sm font-extrabold mt-7 mb-3">Загруженные профили</h3>${ids.length ? `<div class="grid grid-cols-3 gap-3">${ids.map((id) => { const employee = state.employees.find((item) => String(item.employee_id) === String(id)); return `<button type="button" class="rounded-xl border border-surface-line p-4 text-left hover:border-halyk-400 hover:bg-halyk-50 transition-colors uploaded-person" data-employee-id="${esc(id)}"><span class="block text-sm font-extrabold">${esc(employee?.full_name || id)}</span><span class="block text-[11px] text-ink-500 mt-1">${esc(employee?.role || "Открыть профиль")}</span><span class="inline-flex items-center gap-1 text-[11px] font-extrabold text-halyk-700 mt-3">Профиль ${icon("arrow", "w-3.5 h-3.5")}</span></button>`; }).join("")}</div>` : '<p class="text-xs text-ink-500">Новых профилей в ответе нет.</p>'}${warnings.length ? `<div class="mt-6 rounded-xl bg-[#FFF4DF] p-4 text-xs text-[#875700]"><p class="font-extrabold mb-2">Предупреждения</p><ul class="list-disc pl-5 space-y-1">${warnings.map((warning) => `<li>${esc(typeof warning === "string" ? warning : JSON.stringify(warning))}</li>`).join("")}</ul></div>` : ""}</section>`;
  }

  async function refreshAfterDataChange() {
    ++state.selectionVersion;
    state.selectedId = null;
    state.profile = null;
    state.recommendations = null;
    state.hrLoaded = false;
    $("#employee-search").value = "";
    show($("#employee-empty"), true);
    show($("#employee-content"), false);
    await loadEmployees();
    if (state.tab === "hr") loadHr();
  }

  async function uploadFiles(event) {
    event?.preventDefault();
    if (!state.selectedFiles.length) { $("#data-mount").innerHTML = errorCard("Выберите один или несколько файлов JSON или CSV.", "upload", "Файлы не выбраны"); return; }
    if (state.selectedFiles.some((file) => !/\.(json|csv)$/i.test(file.name))) { $("#data-mount").innerHTML = errorCard("Поддерживаются только файлы .json и .csv.", "upload", "Неподдерживаемый формат"); return; }
    const form = new FormData();
    state.selectedFiles.forEach((file) => form.append("files", file));
    const button = $("#upload-button");
    button.disabled = true;
    button.textContent = "Загружаем…";
    $("#data-mount").innerHTML = skeleton("table");
    try {
      const result = await api("/api/upload", { method:"POST", body:form });
      state.uploadResult = result;
      await refreshAfterDataChange();
      renderUploadResult(result);
      state.selectedFiles = [];
      $("#upload-files").value = "";
      renderSelectedFiles();
    } catch (error) {
      $("#data-mount").innerHTML = errorCard(error.message, "upload", "Загрузка не удалась");
    } finally {
      button.disabled = false;
      button.textContent = "Загрузить";
    }
  }

  async function resetData() {
    const button = $("#reset-button");
    button.disabled = true;
    button.textContent = "Восстанавливаем…";
    $("#data-mount").innerHTML = skeleton("table");
    try {
      const result = await api("/api/reset", { method:"POST" });
      if (result?.ok !== true) throw new Error("Сервер не подтвердил сброс данных.");
      state.uploadResult = null;
      await refreshAfterDataChange();
      $("#data-mount").innerHTML = `<div class="card p-6 flex items-center gap-3 text-sm font-extrabold text-halyk-700">${icon("check")} Исходные данные восстановлены.</div>`;
    } catch (error) {
      $("#data-mount").innerHTML = errorCard(error.message, "reset", "Не удалось сбросить данные");
    } finally {
      button.disabled = false;
      button.textContent = "Сбросить к исходным данным";
    }
  }

  document.querySelectorAll('input[name="role"]').forEach((input) => input.addEventListener("change", () => setRole(input.value)));
  document.querySelectorAll(".nav-tab").forEach((button) => button.addEventListener("click", () => setTab(button.dataset.tab)));
  $("#employee-search").addEventListener("focus", openOptions);
  $("#employee-search").addEventListener("input", openOptions);
  $("#employee-search").addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeOptions();
    if (event.key === "ArrowDown") { event.preventDefault(); openOptions(); $("#employee-options .selector-option")?.focus(); }
  });
  $("#employee-options").addEventListener("keydown", (event) => {
    const options = [...$("#employee-options").querySelectorAll(".selector-option")];
    const index = options.indexOf(document.activeElement);
    if (event.key === "Escape") { closeOptions(); $("#employee-search").focus(); }
    if (event.key === "ArrowDown" && index < options.length - 1) { event.preventDefault(); options[index + 1].focus(); }
    if (event.key === "ArrowUp") { event.preventDefault(); if (index > 0) options[index - 1].focus(); else $("#employee-search").focus(); }
  });
  $("#employee-options").addEventListener("click", (event) => { const option = event.target.closest("[data-employee-id]"); if (option) selectEmployee(option.dataset.employeeId); });
  document.addEventListener("click", (event) => { if (!$("#employee-picker").contains(event.target)) closeOptions(); });
  $("#recommend-mount").addEventListener("click", (event) => { const button = event.target.closest(".complete-button"); if (button) completeActivity(button.dataset.eventId, button); });
  $("#skills-mount").addEventListener("click", (event) => { if (event.target.closest("#toggle-skills")) { state.showAllSkills = !state.showAllSkills; renderSkills(); } });
  $("#hr-mount").addEventListener("click", (event) => { const person = event.target.closest(".hr-person"); if (person) selectEmployee(person.dataset.employeeId); });
  $("#upload-files").addEventListener("change", (event) => { state.selectedFiles = [...event.target.files]; renderSelectedFiles(); });
  const dropZone = $("#drop-zone");
  ["dragenter", "dragover"].forEach((name) => dropZone.addEventListener(name, (event) => { event.preventDefault(); dropZone.classList.add("drag-over"); }));
  ["dragleave", "drop"].forEach((name) => dropZone.addEventListener(name, (event) => { event.preventDefault(); dropZone.classList.remove("drag-over"); }));
  dropZone.addEventListener("drop", (event) => { state.selectedFiles = [...event.dataTransfer.files]; renderSelectedFiles(); });
  $("#upload-form").addEventListener("submit", uploadFiles);
  $("#reset-button").addEventListener("click", resetData);
  $("#data-mount").addEventListener("click", (event) => { const person = event.target.closest(".uploaded-person"); if (person) selectEmployee(person.dataset.employeeId); });
  document.addEventListener("click", (event) => {
    const retry = event.target.closest("[data-retry]");
    if (!retry) return;
    const action = retry.dataset.retry;
    if (action === "employees") loadEmployees();
    if (action === "profile" || action === "history") loadProfile();
    if (action === "recommend") loadRecommendations();
    if (action === "hr") loadHr();
    if (action === "upload") uploadFiles();
    if (action === "reset") resetData();
  });

  loadEmployees();
})();
