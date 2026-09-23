async function api(path, options = {}) {
  try {
    const response = await fetch(path, options);
    const contentType = response.headers.get("content-type") || "";
    const body = contentType.includes("json") ? await response.json() : await response.text();
    if (!response.ok) {
      const detail = body && typeof body === "object" ? (body.detail ?? body.message ?? body.error) : body;
      const issues = Array.isArray(body?.errors) ? body.errors.map((item) => item.msg).filter(Boolean).join("; ") : "";
      const message = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((item) => item.msg || item.message || JSON.stringify(item)).join("; ") : "";
      throw new Error([message, issues].filter(Boolean).join(" — ") || `Ошибка сервера (${response.status}).`);
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
    selectionVersion:0, hrLoaded:false, hrShowAllSkills:false, hrSkills:[], uploadResult:null, selectedFiles:[],
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
  const number = (value, digits = 0) => value === null || value === undefined || value === "" ? "—" : Number.isFinite(Number(value)) ? new Intl.NumberFormat("ru-RU", { maximumFractionDigits:digits }).format(Number(value)) : "—";
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

  function icon(name, className = "icon") {
    const paths = {
      arrow:'<path d="M5 12h14m-6-6 6 6-6 6"/>',
      check:'<path d="m5 12 4 4L19 6"/>',
      close:'<path d="M6 6l12 12M18 6L6 18"/>',
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
    if (kind === "profile") return '<div class="card skeleton-profile"><div class="skeleton skeleton-ring"></div><div class="skeleton-lines"><div class="skeleton skeleton-line skeleton-line--wide"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line--short"></div></div><div class="skeleton-lines"><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div></div></div>';
    if (kind === "quests") return [0, 1, 2].map(() => '<div class="card skeleton-quest"><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line--wide"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div></div>').join("");
    if (kind === "skills") return '<div class="card skeleton-list"><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div></div>';
    return '<div class="card skeleton-list"><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div></div>';
  }

  function errorCard(message, action, title = "Не удалось загрузить данные") {
    return `<div class="card error-card" role="alert"><div class="error-card__body"><span class="error-card__icon">${icon("alert")}</span><div><h3>${esc(title)}</h3><p>${esc(message)}</p></div></div><button type="button" class="button-secondary" data-retry="${esc(action)}">Повторить</button></div>`;
  }

  function emptyCard(title, description) {
    return `<div class="card empty-card"><span class="empty-card__icon">${icon("target")}</span><h3>${esc(title)}</h3><p>${esc(description)}</p></div>`;
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
    $("#employee-list-status").innerHTML = '<span class="skeleton skeleton-inline" aria-label="Загружаем сотрудников"></span>';
    $("#employee-list-error").innerHTML = "";
    try {
      const result = await api("/api/employees?limit=1000");
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
    const matches = state.employees.filter((employee) => String(employee.name || "").toLocaleLowerCase("ru").includes(query));
    $("#employee-options").innerHTML = matches.length ? matches.map((employee) => `<button type="button" class="selector-option" role="option" data-employee-id="${esc(employee.employee_id)}"><span><strong>${esc(employee.name)}</strong><small>${esc(employee.role)} · ${esc(employee.grade)}</small></span>${employee.has_recommendation === false ? '<span class="selector-option__note">Без рекомендаций</span>' : icon("arrow", "icon--sm")}</button>`).join("") : '<p class="selector-empty">По вашему запросу сотрудники не найдены.</p>';
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
    $("#employee-search").value = summary?.name || String(id);
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
      $("#recommend-mount").innerHTML = `<div class="grid-full">${errorCard(error.message, "recommend", "Рекомендации недоступны")}</div>`;
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
    const initials = String(profile.name || "?").trim().split(/\s+/).slice(0, 2).map((piece) => piece[0]).join("").toUpperCase();
    const nextGrade = profile.next_grade;
    const progressTitle = nextGrade ? `Прогресс к ${nextGrade}` : "Следующий грейд не задан";
    const gapDescription = nextGrade
      ? criticalCount ? `До ${nextGrade} осталось закрыть ${criticalSkillPhrase(criticalCount)}` : `Критичные навыки для ${nextGrade} закрыты`
      : "Требования следующего грейда не переданы API.";
    $("#profile-mount").innerHTML = `<section class="profile-hero" aria-label="Профиль сотрудника">
      <div class="profile-ring" role="progressbar" aria-label="Прогресс к следующему грейду" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(progress * 100)}"><svg viewBox="0 0 128 128" aria-hidden="true"><circle cx="64" cy="64" r="52" stroke="rgba(255,255,255,.24)" stroke-width="9" fill="none"/><circle class="ring-progress" cx="64" cy="64" r="52" stroke="white" stroke-linecap="round" stroke-width="9" fill="none" stroke-dasharray="${circleLength}" stroke-dashoffset="${circleLength * (1 - initial)}"/></svg><div class="profile-ring__center"><span class="profile-ring__value">${number(progress * 100)}%</span><span class="profile-ring__caption">до грейда</span></div></div>
      <div class="profile-main"><div><p class="profile-kicker">Маршрут развития · ${esc(initials)}</p><h2>${esc(profile.name)}</h2><div class="profile-meta"><span>${esc(profile.role)}</span>${profile.tenure_months != null ? `<span class="profile-meta__dot"></span><span>${number(profile.tenure_months)} мес. в компании</span>` : ""}</div></div><div class="grade-path"><span class="grade-pill">${esc(profile.grade)}</span>${nextGrade ? `<span aria-hidden="true">→</span><span class="grade-pill grade-pill--next">${esc(nextGrade)}</span>` : ""}</div><div class="profile-xp"><div class="profile-xp__labels"><span>${esc(progressTitle)}</span><span>${number(progress * 100)}%</span></div><div class="profile-xp__track"><div class="xp-fill" style="width:${initial * 100}%"></div></div><p class="profile-gap-note">${esc(gapDescription)}</p></div></div>
      <div class="profile-side">${nextGrade ? `<div class="profile-fact"><small>Следующий грейд</small><strong>${esc(nextGrade)}</strong></div>` : ""}<div class="profile-fact"><small>Критичных разрывов</small><strong>${number(criticalCount)}</strong></div></div>
    </section>`;
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
      return `<article class="quest-card"><div class="quest-card__top"><span class="quest-card__label">Квест ${String(index + 1).padStart(2, "0")}</span><span class="quest-card__icon">${icon("spark", "icon--sm")}</span></div><h3>${esc(item.title)}</h3><div class="quest-meta"><span>${esc(labels[item.type] || prettyKey(item.type))}</span>${item.duration != null ? `<span>${number(item.duration, 1)} ч.</span>` : ""}</div><p class="quest-explanation">${esc(item.explanation || "Объяснение для активности пока не предоставлено.")}</p><div class="quest-reasons"><h4>Почему подходит</h4><div class="quest-factors">${factors.length ? factors.map(([key, value]) => `<span class="factor-pill" title="${esc(factorText(value))}">${esc(prettyKey(key))}: ${esc(factorText(value))}</span>`).join("") : '<span class="muted">Факторы не переданы.</span>'}</div></div><div class="quest-actions"><button class="button-primary complete-button" type="button" data-event-id="${esc(item.event_id)}">${icon("play", "icon--sm")} Пройти</button></div></article>`;
    }).join("") : `<div class="grid-full">${emptyCard("Нет рекомендаций", "Для текущих навыков и доступных активностей подходящий следующий шаг не найден.")}</div>`;
    const excluded = Array.isArray(result.not_recommended) ? result.not_recommended : [];
    show($("#not-recommended"), excluded.length > 0);
    $("#not-recommended-count").textContent = excluded.length ? `${excluded.length} активности` : "";
    $("#not-recommended-mount").innerHTML = excluded.map((item) => `<div class="excluded-row"><strong>${esc(item.title)}</strong><p>${esc(item.reason || "Причина не указана.")}</p></div>`).join("");
  }

  function skillCard(skill, starts) {
    const current = starts.has(String(skill.code)) ? starts.get(String(skill.code)) : Number(skill.current);
    const hasTarget = Number.isInteger(skill.required_next);
    const required = hasTarget ? clamp(skill.required_next, 0, 5) : null;
    const gap = Number(skill.gap) > 0;
    const stateText = gap ? `Разрыв ${number(skill.gap)}` : hasTarget ? "Цель закрыта" : "Цель не задана";
    return `<div class="skill-row" data-skill-id="${esc(skill.code)}"><div class="skill-name"><span title="${esc(skill.name)}">${esc(skill.name)}</span>${skill.critical ? `<span class="skill-critical" title="Критичный навык" aria-label="Критичный навык">${icon("shield", "icon--sm")}</span>` : ""}</div><div class="skill-meter">${[1, 2, 3, 4, 5].map((level) => `<span class="segment ${level <= current ? "filled" : level <= required ? "target-gap" : ""}" data-level="${level}"></span>`).join("")}${hasTarget ? `<span class="skill-marker" style="left:${required * 20}%" title="Требуемый уровень ${required}" aria-hidden="true"></span>` : ""}</div><div class="skill-value"><span>${number(skill.current)}<small>/${hasTarget ? number(required) : "—"}</small></span><span class="skill-chip ${gap ? "skill-chip--gap" : ""}">${esc(stateText)}</span></div></div>`;
  }

  function renderSkills(updates = []) {
    const skills = Array.isArray(state.profile?.skills) ? state.profile.skills : [];
    if (!skills.length) { $("#skills-mount").innerHTML = emptyCard("Навыки не указаны", "Загрузите данные о навыках сотрудника."); return; }
    const gaps = skills.filter((skill) => Number(skill.gap) > 0);
    const others = skills.filter((skill) => Number(skill.gap) <= 0);
    const visible = state.showAllSkills ? [...gaps, ...others] : gaps;
    const starts = new Map(updates.map((item) => [String(item.code), Number(item.before)]));
    $("#skills-mount").innerHTML = `<div class="card skills-panel"><div class="panel-heading"><div><h2>${gaps.length} ${skillWord(gaps.length)} с разрывом</h2><p>Пять сегментов — уровни 1–5. Риска показывает цель следующего грейда.</p></div><div class="skill-legend"><span><i class="legend-swatch"></i>Текущий</span><span><i class="legend-swatch legend-swatch--gap"></i>Разрыв</span><span><i class="legend-swatch legend-swatch--target"></i>Цель</span></div></div>${visible.length ? `<div>${visible.map((skill) => skillCard(skill, starts)).join("")}</div>` : '<p class="muted">Разрывов по навыкам нет. Все требуемые уровни достигнуты.</p>'}${others.length ? `<button id="toggle-skills" class="button-secondary skills-toggle" type="button">${state.showAllSkills ? "Скрыть навыки без разрыва" : `Показать все навыки (${skills.length})`}${icon("chevron", "icon--sm")}</button>` : ""}</div>`;
    if (updates.length) requestAnimationFrame(() => requestAnimationFrame(() => {
      updates.forEach((update) => {
        const row = [...document.querySelectorAll("[data-skill-id]")].find((item) => item.dataset.skillId === String(update.code));
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
    const summary = [
      { label:"Посещено", status:"completed", value:stats.attended },
      { label:"Пропущено / прервано", status:"no_show", value:stats.skipped },
      { label:"Отказ", status:"declined", value:stats.declined },
    ];
    const rows = history.map((item) => {
      const gains = item.skills_gained && typeof item.skills_gained === "object" ? Object.entries(item.skills_gained) : [];
      const gainedText = gains.map(([code, gain]) => {
        const name = profile.skills?.find((skill) => skill.code === code)?.name || code;
        return `+${number(gain)} ${esc(name)}`;
      }).join(", ");
      return `<div class="history-row"><span class="history-dot"></span><div><strong>${esc(item.title)}</strong><small>${esc(date(item.completed_at))}${gainedText ? ` · ${gainedText}` : ""}</small></div><span class="status-pill">Завершено</span></div>`;
    });
    $("#history-mount").innerHTML = `<div class="card history-panel"><div class="history-stats">${summary.map((item) => `<div class="history-stat"><strong>${number(item.value)}</strong><span>${esc(item.label)}</span></div>`).join("")}</div>${rows.length ? rows.join("") : '<p class="muted">Завершённых активностей пока нет.</p>'}<p class="history-note">Отдельные записи о пропусках, отказах, просроченных и текущих активностях API профиля не предоставляет.</p></div>`;
  }

  function toast(message) {
    const node = document.createElement("div");
    node.className = "toast-item";
    node.innerHTML = `${icon("check", "icon")}<span>${esc(message)}</span>`;
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
      const names = new Map((state.profile.skills || []).map((skill) => [skill.code, skill.name]));
      state.recommendations = { llm_used:result.llm_used, recommendations:Array.isArray(result.new_recommendations) ? result.new_recommendations : [], not_recommended:[] };
      renderRecommendations();
      $("#profile-mount").innerHTML = skeleton("profile");
      $("#skills-mount").innerHTML = skeleton("skills");
      $("#history-mount").innerHTML = skeleton("history");
      try {
        const fresh = await api(`/api/employees/${encodeURIComponent(employeeId)}`);
        if (version !== state.selectionVersion) return;
        state.profile = fresh;
        state.showAllSkills = true;
        renderProfile(result.trajectory?.previous_progress_to_next_grade ?? null);
        renderSkills(updates);
        renderHistory();
        const gains = updates.filter((item) => Number(item.after) > Number(item.before)).map((item) => `+${number(Number(item.after) - Number(item.before))} ${names.get(item.code) || item.code}`);
        toast(gains.length ? gains.join(" · ") : "Активность выполнена");
      } catch (error) {
        const card = errorCard(`Активность сохранена, но профиль не обновился: ${error.message}`, "profile", "Обновление недоступно");
        $("#profile-mount").innerHTML = card;
        $("#skills-mount").innerHTML = emptyCard("Навыки не обновлены", "Повторите загрузку профиля.");
        $("#history-mount").innerHTML = emptyCard("История не обновлена", "Повторите загрузку профиля.");
      }
    } catch (error) {
      button.disabled = false;
      button.innerHTML = `${icon("play", "icon--sm")} Пройти`;
      $("#recommend-mount").insertAdjacentHTML("afterbegin", `<div class="grid-full">${errorCard(error.message, "recommend", "Не удалось завершить активность")}</div>`);
    }
  }

  function hrReason(reason) {
    const value = String(reason || "").toLocaleLowerCase("ru");
    if (/похожих активност|пропуск|прерыван|отказ|истори/.test(value)) return { label:"история", summary:"История участия снизила приоритет", category:"history" };
    if (/нет доступных активност/.test(value)) return { label:"нет активностей", summary:"Нет доступных активностей для оставшихся разрывов", category:"availability" };
    if (/все требования/.test(value)) return { label:"другое", summary:"Требования целевого грейда выполнены", category:"other" };
    if (/не загружены требования/.test(value)) return { label:"другое", summary:"Нет требований следующего грейда", category:"other" };
    return { label:"другое", summary:"Причина указана в подробностях", category:"other" };
  }

  function renderHrSkills(skills) {
    const shown = state.hrShowAllSkills ? skills : skills.slice(0, 8);
    const rows = shown.map((item) => {
      const average = Number(item.avg_level);
      const required = Number(item.required_avg);
      const gap = Math.max(0, required - average);
      const intensity = clamp(gap / 5, 0, 1);
      return `<div class="hr-skill-row hr-skill-grid" role="row">
        <div class="hr-skill-name" role="cell">${esc(item.name)}</div>
        <div class="hr-skill-level" role="cell"><div class="hr-skill-meter" role="img" aria-label="Средний уровень ${number(average, 1)} из 5, требуется ${number(required, 1)} из 5"><span class="hr-skill-fill" style="width:${clamp(average / 5 * 100, 0, 100)}%;opacity:${(0.42 + intensity * 0.58).toFixed(2)}"></span><span class="hr-skill-target" style="left:${clamp(required / 5 * 100, 0, 100)}%"></span></div><div class="hr-skill-scale"><span>0</span><span>5</span></div></div>
        <div class="hr-skill-number" role="cell">${number(average, 1)}</div>
        <div class="hr-skill-number" role="cell">${number(required, 1)}</div>
        <div class="hr-skill-number hr-skill-count" role="cell">${number(item.employees_below)}</div>
      </div>`;
    }).join("");
    return `<div class="hr-skill-table" role="table" aria-label="Проседающие навыки"><div class="hr-skill-head hr-skill-grid" role="row"><span role="columnheader">Навык</span><span role="columnheader">Уровень · 0–5</span><span role="columnheader" class="hr-right">Средний</span><span role="columnheader" class="hr-right">Нужно</span><span role="columnheader" class="hr-right">С разрывом</span></div>${rows || '<p class="hr-empty">Навыков с разрывом сейчас нет.</p>'}</div>${skills.length > 8 ? `<button type="button" class="hr-more" data-hr-skills-toggle aria-expanded="${state.hrShowAllSkills}">${state.hrShowAllSkills ? "Свернуть список" : `Показать все ${number(skills.length)}`}</button>` : ""}`;
  }

  function renderHrNoRecommendation(items) {
    if (!items.length) return '<p class="hr-empty">У каждого сотрудника есть рекомендованный шаг.</p>';
    return `<table class="hr-table hr-no-step-table"><thead><tr><th>Сотрудник</th><th>Роль</th><th>Причина</th></tr></thead><tbody>${items.map((item, index) => {
      const reason = hrReason(item.reason);
      return `<tr class="hr-expand-row" data-hr-reason="${index}" tabindex="0" aria-expanded="false"><td><a href="#employee-panel" class="hr-person" data-employee-id="${esc(item.employee_id)}">${esc(item.name)}</a></td><td>${esc(item.role)}</td><td><div class="hr-reason-brief"><span class="hr-reason-tag hr-reason-tag--${reason.category}">${reason.label}</span><span class="hr-reason-summary">${reason.summary}</span><span class="hr-reason-chevron" aria-hidden="true">⌄</span></div></td></tr><tr class="hr-reason-detail" data-hr-detail="${index}" hidden><td colspan="3"><strong>Полная причина</strong><p>${esc(item.reason || "Причина пока не указана.")}</p></td></tr>`;
    }).join("")}</tbody></table>`;
  }

  function renderHrParticipation(items) {
    if (!items.length) return '<p class="hr-empty">Данных об участии пока нет.</p>';
    const resolved = (item) => Number(item.attended) + Number(item.skipped) + Number(item.declined);
    const sorted = [...items].sort((a, b) => (resolved(a) === 0) - (resolved(b) === 0) || Number(a.rate) - Number(b.rate) || String(a.title).localeCompare(String(b.title), "ru") || String(a.event_id).localeCompare(String(b.event_id)));
    return `<table class="hr-table hr-participation-table"><thead><tr><th>Активность</th><th class="hr-right">Участие</th><th class="hr-right">Посещено</th><th class="hr-right">Пропущено</th><th class="hr-right">Отказ</th></tr></thead><tbody>${sorted.map((item) => {
      const rate = clamp(Number(item.rate) * 100, 0, 100);
      const status = rate < 50 ? "low" : "high";
      return `<tr><td class="hr-activity-title">${esc(item.title)}</td><td>${resolved(item) ? `<div class="hr-rate hr-rate--${status}"><span class="hr-rate-track"><span style="width:${rate}%"></span></span><span class="hr-rate-number">${number(rate)}%</span></div>` : '<span class="hr-rate-empty">Нет данных</span>'}</td><td class="hr-right hr-num">${number(item.attended)}</td><td class="hr-right hr-num">${number(item.skipped)}</td><td class="hr-right hr-num">${number(item.declined)}</td></tr>`;
    }).join("")}</tbody></table>`;
  }

  async function loadHr() {
    state.hrLoaded = false;
    $("#hr-mount").innerHTML = `<div class="hr-dashboard"><div class="hr-stats">${[0, 1, 2].map(() => '<div class="card hr-stat"><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line skeleton-line--wide"></div></div>').join("")}</div>${skeleton("table")}</div>`;
    try {
      const data = await api("/api/hr/overview");
      if (state.role !== "hr") return;
      const totals = data.totals || {};
      const weak = Array.isArray(data.weakest_skills) ? data.weakest_skills.filter((item) => Number(item.employees_below) > 0) : [];
      state.hrSkills = weak;
      const without = Array.isArray(data.no_recommendation) ? data.no_recommendation : [];
      const participation = Array.isArray(data.activity_participation) ? data.activity_participation : [];
      const cards = [
        ["Сотрудников", totals.employees, "Профилей в обзоре"],
        ["С разрывами", totals.with_gaps, totals.employees == null ? "Есть разрыв до следующего грейда" : `Из ${number(totals.employees)} сотрудников`],
        ["Без рекомендованного шага", without.length, "Без предложенной активности"],
      ];
      $("#hr-mount").innerHTML = `<div class="hr-dashboard">
        <div class="hr-stats">${cards.map(([label, value, note]) => `<div class="card hr-stat"><p class="hr-stat-label">${esc(label)}</p><strong class="hr-stat-value">${value == null ? "Нет данных" : number(value)}</strong><p class="hr-stat-note">${esc(note)}</p></div>`).join("")}</div>
        <section class="card hr-primary"><div class="hr-section-heading"><div><p class="hr-section-kicker">Компетенции команды</p><h2 class="section-title">Проседающие навыки</h2><p>Средний уровень по навыку и требование следующего грейда; риска показывает цель.</p></div><span class="hr-heading-count">${number(weak.length)} ${skillWord(weak.length)}</span></div><div id="hr-skills-list">${renderHrSkills(weak)}</div></section>
        <div class="hr-lower-grid">
          <section class="card hr-panel"><div class="hr-section-heading"><div><h2 class="section-title">Без рекомендованного шага</h2><p>Причины, по которым следующий шаг пока не предложен.</p></div><span class="hr-heading-count">${number(without.length)}</span></div><div class="hr-panel-scroll">${renderHrNoRecommendation(without)}</div></section>
          <section class="card hr-panel"><div class="hr-section-heading"><div><h2 class="section-title">Участие по активностям</h2><p>Сначала активности с самым низким участием.</p></div><span class="hr-heading-count">${number(participation.length)}</span></div><div class="hr-panel-scroll">${renderHrParticipation(participation)}</div></section>
        </div>
      </div>`;
      state.hrLoaded = true;
    } catch (error) {
      $("#hr-mount").innerHTML = errorCard(error.message, "hr", "Обзор HR недоступен");
    }
  }

  function renderSelectedFiles() {
    const files = state.selectedFiles;
    $("#selected-files").innerHTML = files.length ? files.map((file) => `<div class="selected-file"><span class="selected-file__type">${esc(file.name.split(".").pop().toUpperCase())}</span><span><strong>${esc(file.name)}</strong><small>${number(file.size / 1024, 1)} КБ</small></span><span class="selected-file__status">Выбран</span></div>`).join("") : "Файлы пока не выбраны.";
  }

  function renderUploadResult(result) {
    const loaded = result.loaded || {};
    const ids = Array.isArray(result.employee_ids) ? result.employee_ids : [];
    const warnings = Array.isArray(result.warnings) ? result.warnings : [];
    $("#data-mount").innerHTML = `<section class="card upload-result"><h2>Загрузка завершена</h2><p class="muted">Проверьте загруженные записи и откройте профиль.</p><div class="upload-counts">${[["Сотрудники", loaded.employees], ["Активности", loaded.events], ["Навыки", loaded.skills], ["Профили ролей", loaded.role_profiles], ["Строки истории", loaded.history_rows]].map(([label, value]) => `<div class="upload-count"><strong>${number(value)}</strong><span>${esc(label)}</span></div>`).join("")}</div><h3>Загруженные профили</h3>${ids.length ? `<div class="uploaded-grid">${ids.map((id) => { const employee = state.employees.find((item) => String(item.employee_id) === String(id)); return `<button type="button" class="uploaded-person" data-employee-id="${esc(id)}"><strong>${esc(employee?.name || id)}</strong>${employee?.role ? `<small>${esc(employee.role)}</small>` : ""}<span>Открыть профиль ${icon("arrow", "icon--sm")}</span></button>`; }).join("")}</div>` : '<p class="muted">Новых профилей в ответе нет.</p>'}${warnings.length ? `<div class="warnings"><strong>Предупреждения</strong><ul>${warnings.map((warning) => `<li>${esc(typeof warning === "string" ? warning : JSON.stringify(warning))}</li>`).join("")}</ul></div>` : ""}</section>`;
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
    const allowedNames = new Set(["employees.json", "events.json", "skills.json", "activity_history.csv"]);
    if (state.selectedFiles.some((file) => !allowedNames.has(file.name))) { $("#data-mount").innerHTML = errorCard("Поддерживаются только employees.json, events.json, skills.json и activity_history.csv.", "upload", "Неподдерживаемое имя файла"); return; }
    if (new Set(state.selectedFiles.map((file) => file.name)).size !== state.selectedFiles.length) { $("#data-mount").innerHTML = errorCard("Каждый тип файла можно загрузить только один раз за запрос.", "upload", "Повторяющиеся файлы"); return; }
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
      if (result?.status !== "ok") throw new Error("Сервер не подтвердил сброс данных.");
      state.uploadResult = null;
      await refreshAfterDataChange();
      $("#data-mount").innerHTML = `<div class="card data-success">${icon("check")} Исходные данные восстановлены.</div>`;
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
  $("#hr-mount").addEventListener("click", (event) => {
    const person = event.target.closest(".hr-person");
    if (person) { event.preventDefault(); selectEmployee(person.dataset.employeeId); return; }
    if (event.target.closest("[data-hr-skills-toggle]")) {
      state.hrShowAllSkills = !state.hrShowAllSkills;
      $("#hr-skills-list").innerHTML = renderHrSkills(state.hrSkills || []);
      return;
    }
    const row = event.target.closest("[data-hr-reason]");
    if (row) {
      const detail = $("#hr-mount").querySelector(`[data-hr-detail="${row.dataset.hrReason}"]`);
      detail.hidden = !detail.hidden;
      row.setAttribute("aria-expanded", String(!detail.hidden));
    }
  });
  $("#hr-mount").addEventListener("keydown", (event) => {
    if ((event.key === "Enter" || event.key === " ") && event.target.matches("[data-hr-reason]")) { event.preventDefault(); event.target.click(); }
  });
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
