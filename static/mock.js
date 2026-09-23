(() => {
  "use strict";

  const people = [
    ["E0001", "Marat Yessenov", "Backend Development", "Backend Engineer", "Middle", 29, "office", "kk"],
    ["E0002", "Aruzhan Sadykova", "Frontend Development", "Frontend Engineer", "Junior", 11, "hybrid", "ru"],
    ["E0003", "Dias Kairatov", "Data & Analytics", "Data Analyst", "Middle", 22, "office", "en"],
    ["E0004", "Amina Bekzhan", "Quality Assurance", "QA Engineer", "Senior", 43, "hybrid", "ru"],
    ["E0005", "Timur Ospanov", "Product", "Product Manager", "Middle", 27, "office", "kk"],
    ["E0006", "Madina Akhmetova", "People & Culture", "HR Business Partner", "Senior", 51, "hybrid", "ru"],
    ["E0007", "Erlan Zhumabayev", "Sales", "Sales Manager", "Lead", 68, "office", "kk"],
    ["E0008", "Dana Iskakova", "Customer Experience", "Customer Support Specialist", "Junior", 8, "remote", "ru"],
  ];

  const commonSkills = [
    ["Communication", "soft", "collaboration"],
    ["Problem Solving", "soft", "thinking"],
    ["Collaboration", "soft", "collaboration"],
    ["Ownership", "soft", "leadership"],
  ];
  const roleSkills = {
    "Backend Engineer": [
      ["System Design", "hard", "engineering"], ["Python", "hard", "engineering"],
      ["API Design", "hard", "engineering"], ["Database Optimization", "hard", "engineering"],
      ["Cloud Infrastructure", "hard", "engineering"], ["Security Practices", "hard", "engineering"],
      ["Observability", "hard", "engineering"], ["Code Review", "hard", "engineering"],
    ],
    "Frontend Engineer": [
      ["Frontend Architecture", "hard", "engineering"], ["JavaScript", "hard", "engineering"],
      ["Accessibility", "hard", "engineering"], ["Performance Optimization", "hard", "engineering"],
      ["Design Systems", "hard", "engineering"], ["Testing", "hard", "engineering"],
      ["HTML & CSS", "hard", "engineering"], ["API Integration", "hard", "engineering"],
    ],
    "Data Analyst": [
      ["SQL Analytics", "hard", "analytics"], ["Statistical Modeling", "hard", "analytics"],
      ["Data Storytelling", "hard", "analytics"], ["Experiment Design", "hard", "analytics"],
      ["Python Analytics", "hard", "analytics"], ["Dashboard Design", "hard", "analytics"],
      ["Data Quality", "hard", "analytics"], ["Business Metrics", "hard", "analytics"],
    ],
    "QA Engineer": [
      ["Test Strategy", "hard", "quality"], ["Automation Frameworks", "hard", "quality"],
      ["API Testing", "hard", "quality"], ["Risk Analysis", "hard", "quality"],
      ["Performance Testing", "hard", "quality"], ["Bug Investigation", "hard", "quality"],
      ["Release Quality", "hard", "quality"], ["Test Data", "hard", "quality"],
    ],
    "Product Manager": [
      ["Product Strategy", "hard", "product"], ["Discovery", "hard", "product"],
      ["Prioritization", "hard", "product"], ["Experimentation", "hard", "product"],
      ["Roadmapping", "hard", "product"], ["User Research", "hard", "product"],
      ["Product Analytics", "hard", "product"], ["Stakeholder Alignment", "soft", "product"],
    ],
    "HR Business Partner": [
      ["Workforce Planning", "hard", "people"], ["Employee Relations", "hard", "people"],
      ["Talent Development", "hard", "people"], ["People Analytics", "hard", "people"],
      ["Coaching", "soft", "people"], ["Change Management", "hard", "people"],
      ["Performance Process", "hard", "people"], ["Policy Design", "hard", "people"],
    ],
    "Sales Manager": [
      ["Account Strategy", "hard", "sales"], ["Negotiation", "soft", "sales"],
      ["Pipeline Forecasting", "hard", "sales"], ["Sales Coaching", "soft", "sales"],
      ["CRM Discipline", "hard", "sales"], ["Client Discovery", "soft", "sales"],
      ["Commercial Analysis", "hard", "sales"], ["Presentation", "soft", "sales"],
    ],
    "Customer Support Specialist": [
      ["Case Resolution", "hard", "service"], ["Product Knowledge", "hard", "service"],
      ["Escalation Management", "hard", "service"], ["Service Recovery", "soft", "service"],
      ["Knowledge Base", "hard", "service"], ["Customer Empathy", "soft", "service"],
      ["Ticket Quality", "hard", "service"], ["Response Writing", "soft", "service"],
    ],
  };
  const activityTypes = ["workshop", "course", "compliance", "mentoring", "onboarding", "certification", "meetup"];
  const grades = ["Junior", "Middle", "Senior", "Lead", "Principal"];
  const skillId = (name) => `SK_${name.toUpperCase().replace(/[^A-Z0-9]+/g, "_").replace(/^_|_$/g, "")}`;
  const clone = (value) => structuredClone(value);

  function makeProfile(person, index) {
    const [employee_id, full_name, department, role, grade, tenure_months, work_format, preferred_language] = person;
    const next_grade = grades[Math.min(grades.length - 1, grades.indexOf(grade) + 1)];
    const levels = [[2, 4], [2, 3], [3, 4], [2, 3], [4, 4], [3, 3], [4, 3], [3, 3], [5, 4], [4, 4], [3, 3], [4, 4]];
    const skills = [...roleSkills[role], ...commonSkills].map(([name, type, category], position) => {
      const [current, required_next] = levels[position];
      return { skill_id: skillId(name), name, type, category, current, required_next, gap: Math.max(0, required_next - current), critical: position < 2 };
    });
    const completed_activities = [
      { event_id:`PAST_${employee_id}_1`, title:`${role} Practice Lab`, date:"2026-05-14", status:"completed", skills_gained:[{ skill_id:skills[4].skill_id, name:skills[4].name, gain:1 }] },
      { event_id:`PAST_${employee_id}_2`, title:"Cross-team Case Review", date:"2026-04-21", status:"completed", skills_gained:[{ skill_id:skills[8].skill_id, name:skills[8].name, gain:1 }] },
      { event_id:`PAST_${employee_id}_3`, title:"Leadership Session", date:"2026-03-11", status:"no_show", skills_gained:[] },
      { event_id:`PAST_${employee_id}_4`, title:"Career Mentoring", date:"2026-02-18", status:"dropped", skills_gained:[] },
      { event_id:`PAST_${employee_id}_5`, title:"Product Forum", date:"2026-01-30", status:"declined", skills_gained:[] },
      { event_id:`PAST_${employee_id}_6`, title:"Annual Policy Review", date:"2026-09-10", status:"overdue", skills_gained:[] },
      { event_id:`PAST_${employee_id}_7`, title:"Team Learning Path", date:"2026-09-18", status:"in_progress", skills_gained:[] },
    ];
    return {
      employee_id, full_name, department, role, grade, next_grade, tenure_months,
      work_format, preferred_language,
      career_goal:{ target_role:role, target_grade:next_grade },
      skills, completed_activities,
      history_stats:{ completed:12 + index, no_show:2, dropped:1, declined:1, overdue:1, in_progress:1 },
      trajectory:{ progress_to_next_grade:Math.min(.8, .62 + index * .02), blocking_skills:[] },
    };
  }

  function updateBlocking(profile) {
    profile.trajectory.blocking_skills = profile.skills.filter((skill) => skill.critical && skill.gap > 0).map((skill) => ({ skill_id:skill.skill_id, name:skill.name, current:skill.current, required:skill.required_next }));
  }

  function makeDatabase() {
    const profiles = new Map(people.map((person, index) => {
      const profile = makeProfile(person, index);
      updateBlocking(profile);
      return [profile.employee_id, profile];
    }));
    return { profiles, uploadedIds:[], completions:new Map() };
  }
  let database = makeDatabase();

  function employeeList() {
    return [...database.profiles.values()].map(({ employee_id, full_name, department, role, grade, tenure_months }) => ({
      employee_id, full_name, department, role, grade, tenure_months,
      has_recommendation:employee_id !== "E0008",
    }));
  }

  function recommendationFor(profile, skill, position) {
    const type = activityTypes[(position + [...database.profiles.keys()].indexOf(profile.employee_id)) % activityTypes.length];
    const title = `${skill.name} ${type === "workshop" ? "Workshop" : type === "course" ? "Course" : type === "mentoring" ? "Mentoring" : type === "certification" ? "Certification" : type === "meetup" ? "Meetup" : type === "compliance" ? "Essentials" : "Onboarding"}`;
    return {
      event_id:`EV_${profile.employee_id}_${skill.skill_id}`,
      title, type, format:position % 2 ? "online" : "offline", duration_hours:[8, 6, 4][position],
      mandatory:false, score:Number((.87 - position * .07).toFixed(2)),
      upcoming_sessions:[`2026-10-${String(14 + position * 5).padStart(2, "0")}`],
      factors:{
        gap_closure:{ skill_id:skill.skill_id, name:skill.name, current:skill.current, required:skill.required_next, gain:1 },
        grade_criticality:{ critical_for:profile.next_grade, is_critical:skill.critical },
        history_fit:{ similar_completed:2, similar_no_show:0, note:"проходит активности в срок" },
        achievability:{ max_level:5, reachable:skill.current < 5 },
      },
      explanation:`${skill.name} — ${skill.current} при требуемых ${skill.required_next} для ${profile.next_grade}${skill.critical ? ", и этот навык критичен для грейда" : ""}. Активность поднимает уровень на 1, а две похожие активности сотрудник прошёл в срок.`,
    };
  }

  function recommendations(profile) {
    if (profile.employee_id === "E0008") {
      return { llm_used:true, recommendations:[], not_recommended:[{ event_id:"EV_SUPPORT_ADVANCED", title:"Advanced Escalation Lab", reason:"Для активности пока не подтверждены необходимые базовые навыки." }] };
    }
    const gaps = profile.skills.filter((skill) => skill.gap > 0);
    return {
      llm_used:true,
      recommendations:gaps.slice(0, 3).map((skill, position) => recommendationFor(profile, skill, position)),
      not_recommended:[{ event_id:`EV_SKIP_${profile.employee_id}`, title:"Public Speaking Intensive", reason:`Сначала стоит закрыть блокирующий навык ${gaps[0]?.name || "для следующего грейда"}.` }],
    };
  }

  function hrOverview() {
    return {
      totals:{ employees:200, with_gaps:156, no_recommendation:12 },
      weakest_skills:[
        { skill_id:"SK_SYSTEM_DESIGN", name:"System Design", avg_level:1.8, required_avg:3.2, employees_below:47 },
        { skill_id:"SK_PRODUCT_STRATEGY", name:"Product Strategy", avg_level:2.1, required_avg:3.5, employees_below:39 },
        { skill_id:"SK_DATA_STORYTELLING", name:"Data Storytelling", avg_level:2.3, required_avg:3.4, employees_below:31 },
        { skill_id:"SK_WORKFORCE_PLANNING", name:"Workforce Planning", avg_level:2.5, required_avg:3.6, employees_below:24 },
      ],
      no_recommendation:[
        { employee_id:"E0008", full_name:"Dana Iskakova", role:"Customer Support Specialist", reason:"Не подтверждены базовые навыки для доступных активностей" },
      ],
      activity_participation:[
        { event_id:"EV_012", title:"System Design Workshop", completed:120, no_show:14, dropped:6, declined:5, rate:.83 },
        { event_id:"EV_027", title:"Product Discovery Course", completed:98, no_show:9, dropped:4, declined:8, rate:.82 },
        { event_id:"EV_041", title:"Data Storytelling Lab", completed:74, no_show:6, dropped:5, declined:4, rate:.83 },
      ],
    };
  }

  function complete(employee_id, event_id) {
    const profile = database.profiles.get(String(employee_id));
    if (!profile) throw new Error("Сотрудник не найден.");
    const recommendation = recommendations(profile).recommendations.find((item) => item.event_id === event_id);
    if (!recommendation) throw new Error("Активность больше не доступна для выполнения.");
    const skill = profile.skills.find((item) => item.skill_id === recommendation.factors.gap_closure.skill_id);
    const before = skill.current;
    skill.current = Math.min(5, skill.current + 1);
    skill.gap = Math.max(0, skill.required_next - skill.current);
    const count = (database.completions.get(employee_id) || 0) + 1;
    database.completions.set(employee_id, count);
    profile.trajectory.progress_to_next_grade = Math.min(1, Number((.62 + count * .09 + people.findIndex((person) => person[0] === employee_id) * .02).toFixed(2)));
    updateBlocking(profile);
    profile.history_stats.completed += 1;
    profile.completed_activities.unshift({ event_id, title:recommendation.title, date:"2026-09-23", status:"completed", skills_gained:[{ skill_id:skill.skill_id, name:skill.name, gain:skill.current - before }] });
    return clone({
      updated_skills:[{ skill_id:skill.skill_id, name:skill.name, before, after:skill.current, max_level:5 }],
      trajectory:profile.trajectory,
      new_recommendations:recommendations(profile).recommendations,
    });
  }

  function upload(options) {
    const files = options.body?.getAll?.("files") || [];
    if (!files.length) throw new Error("Выберите хотя бы один файл.");
    for (const id of database.uploadedIds) database.profiles.delete(id);
    database.uploadedIds = [];
    const additions = [
      ["E9001", "Aliya Nurgaliyeva", "Backend Development", "Backend Engineer", "Middle", 18, "office", "kk"],
      ["E9002", "Serik Mukhamedov", "Data & Analytics", "Data Analyst", "Junior", 9, "hybrid", "ru"],
      ["E9003", "Aigerim Tolegen", "Product", "Product Manager", "Senior", 36, "office", "en"],
    ];
    additions.forEach((person, index) => {
      const profile = makeProfile(person, index);
      updateBlocking(profile);
      database.profiles.set(profile.employee_id, profile);
      database.uploadedIds.push(profile.employee_id);
    });
    return { loaded:{ employees:3, events:0, history_rows:12 }, employee_ids:[...database.uploadedIds], warnings:[] };
  }

  window.CareerQuestMock = {
    handle(path, options = {}) {
      const method = (options.method || "GET").toUpperCase();
      if (method === "GET" && path === "/api/employees") return clone(employeeList());
      if (method === "GET" && /^\/api\/employees\/[^/]+$/.test(path)) {
        const id = decodeURIComponent(path.split("/").pop());
        const profile = database.profiles.get(id);
        if (!profile) throw new Error("Сотрудник не найден.");
        return clone(profile);
      }
      if (method === "POST" && path === "/api/recommend") {
        const { employee_id } = JSON.parse(options.body || "{}");
        const profile = database.profiles.get(String(employee_id));
        if (!profile) throw new Error("Сотрудник не найден.");
        return clone(recommendations(profile));
      }
      if (method === "POST" && path === "/api/complete") {
        const { employee_id, event_id } = JSON.parse(options.body || "{}");
        return complete(employee_id, event_id);
      }
      if (method === "GET" && path === "/api/hr/overview") return clone(hrOverview());
      if (method === "POST" && path === "/api/upload") return clone(upload(options));
      if (method === "POST" && path === "/api/reset") { database = makeDatabase(); return { ok:true }; }
      throw new Error(`Неизвестный запрос: ${method} ${path}`);
    },
  };
})();
