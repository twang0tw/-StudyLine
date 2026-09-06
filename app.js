const role = document.body.dataset.page;
const tokenKey = "studyline_auth_token";
const userKey = "studyline_auth_user";

function readStoredUser(key) {
  try {
    return JSON.parse(window.localStorage.getItem(key) || "null");
  } catch {
    return null;
  }
}

function migrateRoleSession() {
  if (window.localStorage.getItem(tokenKey)) return;
  for (const legacyRole of ["student", "ta"]) {
    const legacyToken = window.localStorage.getItem(`studyline_${legacyRole}_token`);
    if (!legacyToken) continue;
    window.localStorage.setItem(tokenKey, legacyToken);
    const legacyUser = window.localStorage.getItem(`studyline_${legacyRole}_user`);
    if (legacyUser) window.localStorage.setItem(userKey, legacyUser);
    for (const staleRole of ["student", "ta"]) {
      window.localStorage.removeItem(`studyline_${staleRole}_token`);
      window.localStorage.removeItem(`studyline_${staleRole}_user`);
    }
    break;
  }
}

migrateRoleSession();
let authToken = window.localStorage.getItem(tokenKey);
let currentUser = readStoredUser(userKey);
let queueToken = window.localStorage.getItem("studyline_queue_token");
let activeSectionId = new URLSearchParams(window.location.search).get("section") || window.localStorage.getItem(`${role}_active_section`);
let activeCourseId = new URLSearchParams(window.location.search).get("course") || window.localStorage.getItem(`${role}_active_course`);
let scheduleWeekOffset = 0;
let scheduleCourseId = null;
let returnCourseId = window.sessionStorage.getItem(`${role}_return_course`);
let pendingShareCode = new URLSearchParams(window.location.search).get("code") || "";
let googleConfig = {
  googleClientId: "YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com",
  googleConfigured: false,
};

const appRoot = document.querySelector("#appRoot");

function headers() {
  return {
    "Content-Type": "application/json",
    ...(authToken ? { "X-User-Token": authToken } : {}),
    ...(queueToken ? { "X-Queue-Token": queueToken } : {}),
  };
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { ...headers(), ...(options.headers || {}) },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(data.detail || `Request failed: ${response.status}`);
  }
  return data;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatDate(dateText) {
  return new Date(`${dateText}T12:00:00`).toLocaleDateString([], {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

function formatTimeRange(section) {
  return `${section.startTime || "--:--"} - ${section.endTime || "--:--"}`;
}

function shareUrl(targetRole, code, sectionId = "") {
  const page = targetRole === "ta" ? "ta.html" : "student.html";
  const url = new URL(`${window.location.origin}/${page}`);
  url.searchParams.set("code", code);
  if (sectionId) {
    url.searchParams.set("section", sectionId);
  }
  return url.toString();
}

async function copyText(value) {
  if (navigator.clipboard) {
    await navigator.clipboard.writeText(value);
  }
}

async function loadGoogleConfig() {
  googleConfig = await api("/api/auth/config");
}

function setActiveSection(sectionId) {
  activeSectionId = sectionId || null;
  if (activeSectionId) {
    activeCourseId = null;
    window.localStorage.removeItem(`${role}_active_course`);
    window.localStorage.setItem(`${role}_active_section`, activeSectionId);
    history.replaceState(null, "", `${role}.html?section=${encodeURIComponent(activeSectionId)}`);
  } else {
    window.localStorage.removeItem(`${role}_active_section`);
    history.replaceState(null, "", `${role}.html`);
  }
}

function setActiveCourse(courseId) {
  activeCourseId = courseId || null;
  activeSectionId = null;
  returnCourseId = null;
  window.sessionStorage.removeItem(`${role}_return_course`);
  window.localStorage.removeItem(`${role}_active_section`);
  if (activeCourseId) {
    window.localStorage.setItem(`${role}_active_course`, activeCourseId);
    history.replaceState(null, "", `${role}.html?course=${encodeURIComponent(activeCourseId)}`);
  } else {
    window.localStorage.removeItem(`${role}_active_course`);
    history.replaceState(null, "", `${role}.html`);
  }
}

function renderShell(title, body) {
  appRoot.innerHTML = `
    <header class="topbar">
      <div>
        <p class="eyebrow">${role === "ta" ? "TA workspace" : "Student workspace"}</p>
        <h2>${title}</h2>
      </div>
      <div class="topbar-status">
        <div class="status-pill"><span class="pulse"></span>${currentUser ? escapeHtml(currentUser.name) : "Signed out"}</div>
        <div class="live-clock"><span>Now</span><strong id="liveClockInline">${new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</strong></div>
      </div>
    </header>
    ${body}
  `;
}

function renderLogin(error = "") {
  renderShell(
    role === "ta" ? "Sign in to manage courses." : "Sign in to join your courses.",
    `
      <section class="panel auth-panel">
        <div>
          <p class="eyebrow">Google Login</p>
          <h3>Continue with your school Google account</h3>
          <p class="muted">StudyLine verifies the Google ID token on the Python backend before creating your app session.</p>
        </div>
        <div id="googleSignInButton"></div>
        ${
          googleConfig.googleConfigured
            ? ""
            : `<p class="form-error">Set GOOGLE_CLIENT_ID in .env before Google login can work. Current placeholder: ${escapeHtml(googleConfig.googleClientId)}</p>`
        }
        ${error ? `<p class="form-error">${escapeHtml(error)}</p>` : ""}
      </section>
    `
  );

  renderGoogleButton();
}

function renderGoogleButton() {
  if (!googleConfig.googleConfigured) {
    return;
  }

  if (!window.google?.accounts?.id) {
    window.setTimeout(renderGoogleButton, 150);
    return;
  }

  window.google.accounts.id.initialize({
    client_id: googleConfig.googleClientId,
    callback: handleGoogleCredential,
  });
  window.google.accounts.id.renderButton(document.querySelector("#googleSignInButton"), {
    theme: "outline",
    size: "large",
    text: "continue_with",
    width: 280,
  });
}

window.handleGoogleCredential = async function handleGoogleCredential(response) {
  try {
    const result = await api("/api/auth/login", {
      method: "POST",
      body: {
        credential: response.credential,
        role,
      },
    });
    authToken = result.token;
    currentUser = result.user;
    window.localStorage.setItem(tokenKey, authToken);
    window.localStorage.setItem(userKey, JSON.stringify(currentUser));
    await afterLogin();
  } catch (error) {
    renderLogin(error.message);
  }
}

async function afterLogin() {
  document.body.classList.toggle("compact-mode", Boolean(currentUser?.preferences?.compactMode));
  if (pendingShareCode) {
    await joinShareCode(pendingShareCode, true);
    pendingShareCode = "";
    return;
  }
  if (activeSectionId) {
    await renderSectionView(activeSectionId);
    return;
  }
  if (activeCourseId) {
    await renderCourseView(activeCourseId);
    return;
  }
  await renderDashboard();
}

async function joinShareCode(code, fromUrl = false) {
  const result = await api("/api/share/join", {
    method: "POST",
    body: { code, role },
  });
  if (result.section) {
    setActiveSection(result.section.id);
    await renderSectionView(result.section.id);
  } else {
    if (fromUrl) {
      history.replaceState(null, "", `${role}.html`);
    }
    await renderDashboard();
  }
}

async function renderDashboard(message = "") {
  const { courses } = await api(`/api/courses?role=${encodeURIComponent(role)}`);
  renderShell(
    role === "ta" ? "Your teaching dashboard." : "Your courses and office hours.",
    `
      <section class="dashboard-actions">
        <form id="shareJoinForm" class="panel inline-form">
          <label>Enter share code<input name="code" type="text" placeholder="${role === "ta" ? "T-C-ABC123 or T-S-ABC123" : "S-C-ABC123 or S-S-ABC123"}" /></label>
          <button class="primary-action" type="submit">Join</button>
        </form>
        ${
          role === "ta"
            ? `<form id="courseForm" class="panel inline-form">
                <label>Course code<input name="code" type="text" placeholder="CS 101" required /></label>
                <label>Title<input name="title" type="text" placeholder="Intro Computer Science" /></label>
                <button class="secondary-action" type="submit">Add Course</button>
              </form>`
            : ""
        }
      </section>
      ${message ? `<p class="notice">${escapeHtml(message)}</p>` : ""}
      <section class="course-list">
        ${courses.length ? courses.map(renderCourseCard).join("") : `<div class="panel empty-state">No courses yet. Use a share code to join one.</div>`}
      </section>
    `
  );

  document.querySelector("#shareJoinForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const code = new FormData(event.currentTarget).get("code");
    await joinShareCode(code);
  });

  document.querySelector("#courseForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await api("/api/courses", {
      method: "POST",
      body: { code: form.get("code"), title: form.get("title") },
    });
    await renderDashboard("Course added.");
  });

  document.querySelectorAll("[data-open-course]").forEach((button) => {
    button.addEventListener("click", () => {
      setActiveCourse(button.dataset.openCourse);
      renderCourseView(button.dataset.openCourse);
    });
  });

  document.querySelectorAll("[data-open-section]").forEach((button) => {
    button.addEventListener("click", () => {
      setActiveSection(button.dataset.openSection);
      renderSectionView(button.dataset.openSection);
    });
  });

  document.querySelectorAll("[data-save-section]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api(`/api/sections/${button.dataset.saveSection}`, {
        method: "PATCH",
        body: { saved: true },
      });
      await renderDashboard("Past section saved permanently.");
    });
  });

  document.querySelectorAll("[data-delete-section]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api(`/api/sections/${button.dataset.deleteSection}`, { method: "DELETE" });
      await renderDashboard("Section deleted.");
    });
  });

  document.querySelectorAll("[data-course-section-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = new FormData(event.currentTarget);
      const result = await api("/api/sections", {
        method: "POST",
        body: {
          courseId: form.dataset.courseSectionForm,
          date: data.get("date"),
          startTime: data.get("startTime"),
          endTime: data.get("endTime"),
          location: data.get("location"),
          zoomLink: data.get("zoomLink"),
        },
      });
      setActiveSection(result.section.id);
      await renderSectionView(result.section.id);
    });
  });

  document.querySelectorAll("[data-edit-section-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = new FormData(event.currentTarget);
      await api(`/api/sections/${form.dataset.editSectionForm}`, {
        method: "PATCH",
        body: {
          date: data.get("date"),
          startTime: data.get("startTime"),
          endTime: data.get("endTime"),
          location: data.get("location"),
          zoomLink: data.get("zoomLink"),
          highlightChange: data.get("highlightChange") === "on",
        },
      });
      await renderDashboard("Section updated.");
    });
  });

  document.querySelectorAll("[data-cancel-section]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api(`/api/sections/${button.dataset.cancelSection}`, {
        method: "PATCH",
        body: { status: "cancelled", highlightChange: true },
      });
      await renderDashboard("Section cancelled.");
    });
  });

  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      await copyText(button.dataset.copy);
      button.textContent = "Copied";
    });
  });
}

function renderCourseCard(course) {
  return `
    <article class="panel course-card course-card-summary">
      <div class="section-heading">
        <div>
          <p class="eyebrow">${escapeHtml(course.code)}</p>
          <h3>${escapeHtml(course.title || course.code)}</h3>
          <p class="muted">${course.upcomingSections?.length || 0} upcoming office-hour section${course.upcomingSections?.length === 1 ? "" : "s"}</p>
        </div>
        <button class="primary-action" data-open-course="${course.id}" type="button">Open course</button>
      </div>
    </article>
  `;
}

async function renderCourseView(courseId, message = "") {
  if (scheduleCourseId !== courseId) scheduleWeekOffset = 0;
  scheduleCourseId = courseId;
  const { courses } = await api(`/api/courses?role=${encodeURIComponent(role)}`);
  const course = courses.find((item) => item.id === courseId);
  if (!course) {
    setActiveCourse(null);
    await renderDashboard("Course not found.");
    return;
  }

  renderShell(
    `${course.code}: ${course.title || course.code}`,
    `
      <button id="backToCourses" class="secondary-action back-button" type="button">Back to courses</button>
      ${message ? `<p class="notice">${escapeHtml(message)}</p>` : ""}
      ${
        role === "ta"
          ? `<section class="course-tools">
              <article class="panel course-share-card">
                <div><p class="eyebrow">Share course</p><h3>Invite students or fellow TAs</h3></div>
                <div class="share-choice-grid">
                  ${renderShareChoice("Students", course.studentShareCode, shareUrl("student", course.studentShareCode))}
                  ${renderShareChoice("TAs", course.taShareCode, shareUrl("ta", course.taShareCode))}
                </div>
              </article>
              <article class="panel add-section-panel">${renderAddSectionForm(course)}</article>
            </section>`
          : ""
      }
      <article class="panel course-schedule-panel">
        <div class="section-heading">
          <div><p class="eyebrow">Schedule</p><h3>Upcoming office hours</h3></div>
          <span class="forecast-note">${course.upcomingSections?.length || 0} scheduled</span>
        </div>
        <div id="courseCalendar">${renderWeekSchedule(course.upcomingSections || [])}</div>
        <details class="schedule-details"><summary>All upcoming sections${role === "ta" ? " · edit and manage" : ""}</summary><div class="schedule-agenda">${(course.upcomingSections || []).map((section) => renderSectionMini(section, true)).join("") || `<p class="muted">No sections scheduled yet.</p>`}</div></details>
      </article>
      <article class="panel course-past-panel">
        <div class="section-heading"><div><p class="eyebrow">Past sections</p><h3>History</h3></div></div>
        <div class="past-list">${renderPastSections(course.pastSections || [])}</div>
      </article>
    `
  );

  document.querySelector("#courseCalendar").addEventListener("click", (event) => {
    const navigation = event.target.closest("[data-week-step]");
    if (navigation) {
      scheduleWeekOffset = navigation.dataset.weekStep === "today" ? 0 : scheduleWeekOffset + Number(navigation.dataset.weekStep);
      document.querySelector("#courseCalendar").innerHTML = renderWeekSchedule(course.upcomingSections || []);
      updateClock();
    }
    const sectionButton = event.target.closest("[data-calendar-section]");
    if (sectionButton) {
      returnCourseId = course.id;
      window.sessionStorage.setItem(`${role}_return_course`, course.id);
      setActiveSection(sectionButton.dataset.calendarSection);
      renderSectionView(sectionButton.dataset.calendarSection);
    }
  });
  updateClock();

  document.querySelector("#backToCourses").addEventListener("click", async () => {
    setActiveCourse(null);
    await renderDashboard();
  });
  document.querySelectorAll("[data-open-section]").forEach((button) => {
    button.addEventListener("click", () => {
      returnCourseId = course.id;
      window.sessionStorage.setItem(`${role}_return_course`, course.id);
      setActiveSection(button.dataset.openSection);
      renderSectionView(button.dataset.openSection);
    });
  });
  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      await copyText(button.dataset.copy);
      button.textContent = "Copied";
    });
  });
  document.querySelectorAll("[data-save-section]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api(`/api/sections/${button.dataset.saveSection}`, { method: "PATCH", body: { saved: true } });
      await renderCourseView(course.id, "Past section saved permanently.");
    });
  });
  document.querySelectorAll("[data-delete-section]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api(`/api/sections/${button.dataset.deleteSection}`, { method: "DELETE" });
      await renderCourseView(course.id, "Section deleted.");
    });
  });
  document.querySelectorAll("[data-cancel-section]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api(`/api/sections/${button.dataset.cancelSection}`, { method: "PATCH", body: { status: "cancelled", highlightChange: true } });
      await renderCourseView(course.id, "Section cancelled.");
    });
  });
  document.querySelectorAll("[data-edit-section-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = new FormData(event.currentTarget);
      await api(`/api/sections/${form.dataset.editSectionForm}`, {
        method: "PATCH",
        body: { date: data.get("date"), startTime: data.get("startTime"), endTime: data.get("endTime"), location: data.get("location"), zoomLink: data.get("zoomLink"), highlightChange: data.get("highlightChange") === "on" },
      });
      await renderCourseView(course.id, "Section updated.");
    });
  });
  document.querySelectorAll("[data-course-section-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = new FormData(event.currentTarget);
      const result = await api("/api/sections", {
        method: "POST",
        body: { courseId: course.id, date: data.get("date"), startTime: data.get("startTime"), endTime: data.get("endTime"), location: data.get("location"), zoomLink: data.get("zoomLink") },
      });
      setActiveSection(result.section.id);
      await renderSectionView(result.section.id);
    });
  });
}

function renderShareChoice(label, code, url) {
  return `
    <div class="share-choice">
      <strong>${label}</strong>
      <code>${escapeHtml(code)}</code>
      <div class="share-row">
        <button class="secondary-action" data-copy="${escapeHtml(code)}" type="button">Copy code</button>
        <button class="secondary-action" data-copy="${escapeHtml(url)}" type="button">Copy URL</button>
      </div>
    </div>`;
}

function localDateKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function scheduleMinutes(time) {
  const [hours, minutes] = time.split(":").map(Number);
  return hours * 60 + minutes;
}

function renderWeekSchedule(sections) {
  const today = new Date();
  const monday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  monday.setDate(monday.getDate() - (monday.getDay() + 6) % 7 + scheduleWeekOffset * 7);
  const dates = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(monday);
    date.setDate(date.getDate() + index);
    return date;
  });
  const weekSections = sections.filter((section) => dates.some((date) => localDateKey(date) === section.date));
  const visibleDates = dates.filter((date, index) => index < 5 || weekSections.some((section) => section.date === localDateKey(date)));
  const startHour = Math.min(8, ...weekSections.map((section) => Math.floor(scheduleMinutes(section.startTime) / 60)));
  const endHour = Math.max(18, ...weekSections.map((section) => Math.ceil(scheduleMinutes(section.endTime) / 60)));
  const height = (endHour - startHour) * 64;
  const range = `${dates[0].toLocaleDateString([], { month: "short", day: "numeric" })} – ${dates[6].toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" })}`;
  return `
    <div class="calendar-toolbar">
      <div><strong aria-live="polite">${range}</strong><p class="muted small">Local time · ${weekSections.length} section${weekSections.length === 1 ? "" : "s"} this week</p></div>
      <div class="share-row"><button class="secondary-action" data-week-step="-1" aria-label="Previous week">‹</button><button class="secondary-action" data-week-step="today">Today</button><button class="secondary-action" data-week-step="1" aria-label="Next week">›</button></div>
    </div>
    ${!weekSections.length ? '<p class="calendar-empty muted small">No sections this week. Browse the next week or expand all upcoming sections below.</p>' : ''}
    <div class="calendar-scroll" tabindex="0" role="region" aria-label="Weekly office hours calendar">
      <div class="time-calendar" style="--day-count: ${visibleDates.length}; --calendar-height: ${height}px">
        <div class="calendar-corner">Time</div>
        ${visibleDates.map((date) => `<div class="calendar-day-heading ${localDateKey(date) === localDateKey(today) ? "is-today" : ""}"><span>${date.toLocaleDateString([], { weekday: "short" })}</span><strong>${date.getDate()}</strong></div>`).join("")}
        <div class="calendar-hours">${Array.from({ length: endHour - startHour }, (_, index) => `<span style="top:${index * 64}px">${String(startHour + index).padStart(2, "0")}:00</span>`).join("")}</div>
        ${visibleDates.map((date) => {
          const key = localDateKey(date);
          const daySections = weekSections.filter((section) => section.date === key).sort((a, b) => a.startTime.localeCompare(b.startTime));
          // Group intersecting sections so every event remains visible and clickable.
          const groups = [];
          daySections.forEach((section) => {
            const start = scheduleMinutes(section.startTime);
            const end = Math.max(scheduleMinutes(section.endTime), start + 30);
            const last = groups[groups.length - 1];
            if (last && start < last.end) {
              last.sections.push(section);
              last.end = Math.max(last.end, end);
            } else groups.push({ end, sections: [section] });
          });
          return `<div class="calendar-day ${key === localDateKey(today) ? "is-today" : ""}" data-calendar-date="${key}" data-start-hour="${startHour}" data-end-hour="${endHour}">
            ${groups.map((group) => group.sections.map((section, index) => {
              const top = (scheduleMinutes(section.startTime) - startHour * 60) / 60 * 64;
              const duration = Math.max(30, scheduleMinutes(section.endTime) - scheduleMinutes(section.startTime)) / 60 * 64;
              const label = `${formatTimeRange(section)} · ${section.location || section.zoomLink || "Location TBD"}${section.changeHighlighted ? ` · Updated: ${section.changeNotice || "Check section details"}` : ""}`;
              return `<button class="calendar-event ${section.changeHighlighted ? "highlighted" : ""}" type="button" data-calendar-section="${escapeHtml(section.id)}" title="${escapeHtml(label)}" aria-label="${escapeHtml(`${formatDate(section.date)} · ${label}`)}" style="top:${top}px;height:${duration}px;left:calc(${index * 100 / group.sections.length}% + 3px);width:calc(${100 / group.sections.length}% - 6px)">${section.changeHighlighted ? '<small class="change-badge">⚠ Updated</small>' : ''}<strong>${escapeHtml(formatTimeRange(section))}</strong><span>${escapeHtml(section.location || section.zoomLink || "Location TBD")}</span></button>`;
            }).join("")).join("")}
            <div class="current-time-line" hidden><span></span></div>
          </div>`;
        }).join("")}
      </div>
    </div>`;
}

function renderSectionChanges(section) {
  if (!section.changeHighlighted) return "";
  const changes = section.changes || [];
  return `<aside class="change-note" aria-label="Section changes">
    <strong class="change-heading">⚠ Section updated</strong>
    ${changes.length ? `<dl class="change-list">${changes.map((change) => `<div><dt>${escapeHtml(change.label)}</dt><dd><span class="change-before">${escapeHtml(change.before || "Not set")}</span><span aria-label="changed to"> → </span><strong>${escapeHtml(change.after || "Not set")}</strong></dd></div>`).join("")}</dl>` : `<p>${escapeHtml(section.changeNotice && section.changeNotice !== "Section details were updated." ? section.changeNotice : "This section was updated before detailed change tracking was available. Check the current details above.")}</p>`}
  </aside>`;
}

function renderSectionMini(section, future) {
  return `
    <div class="section-mini ${section.changeHighlighted ? "highlighted" : ""}">
      <button class="link-button" data-open-section="${section.id}" type="button">
        <strong>${formatDate(section.date)}</strong>
        <span>${formatTimeRange(section)}</span>
        <small>${escapeHtml(section.location || section.zoomLink || "Location TBD")}</small>
      </button>
      ${renderSectionChanges(section)}
      ${
        role === "ta" && future
          ? `
            <details class="mini-editor">
              <summary>Edit</summary>
              ${renderEditSectionForm(section)}
              <button class="danger-action" data-cancel-section="${section.id}" type="button">Cancel Section</button>
            </details>`
          : ""
      }
    </div>
  `;
}

function renderPastSections(sections) {
  if (!sections.length) {
    return `<div class="empty-state">No past participated sections yet.</div>`;
  }
  return sections
    .map(
      (section) => `
        <div class="past-item">
          <div>
            <strong>${formatDate(section.date)} ${formatTimeRange(section)}</strong>
            <span>${escapeHtml(section.location || section.zoomLink || "Location TBD")}</span>
            ${section.saved ? `<small>Saved permanently</small>` : `<small>Auto-deletes after retention window</small>`}
          </div>
          <div class="share-row">
            ${role === "ta" && !section.saved ? `<button class="secondary-action" data-save-section="${section.id}" type="button">Save</button>` : ""}
            <button class="danger-action" data-delete-section="${section.id}" type="button">Delete</button>
          </div>
        </div>
      `
    )
    .join("");
}

function renderAddSectionForm(course) {
  const today = new Date().toISOString().slice(0, 10);
  return `
    <details class="add-section">
      <summary>Add New Section</summary>
      <form class="section-form" data-course-section-form="${course.id}">
        <label>Date<input name="date" type="date" value="${today}" required /></label>
        <label>Start<input name="startTime" type="time" value="10:00" required /></label>
        <label>End<input name="endTime" type="time" value="11:00" required /></label>
        <label>Location<input name="location" type="text" placeholder="Library 204" /></label>
        <label>Zoom link<input name="zoomLink" type="url" placeholder="https://..." /></label>
        <button class="primary-action" type="submit">Create And Open</button>
      </form>
    </details>
  `;
}

function renderEditSectionForm(section) {
  return `
    <form class="section-form compact-form" data-edit-section-form="${section.id}">
      <label>Date<input name="date" type="date" value="${escapeHtml(section.date)}" /></label>
      <label>Start<input name="startTime" type="time" value="${escapeHtml(section.startTime)}" /></label>
      <label>End<input name="endTime" type="time" value="${escapeHtml(section.endTime)}" /></label>
      <label>Location<input name="location" type="text" value="${escapeHtml(section.location || "")}" /></label>
      <label>Zoom<input name="zoomLink" type="url" value="${escapeHtml(section.zoomLink || "")}" /></label>
      <label class="checkbox-line"><input name="highlightChange" type="checkbox" checked /> Highlight this change for students</label>
      <button class="secondary-action" type="submit">Save Changes</button>
    </form>
  `;
}

async function renderSectionView(sectionId) {
  const data = await api(`/api/sections/${sectionId}/state`);
  const { section, course, state } = data;
  if (!section || !course) {
    await renderDashboard("Section not found.");
    return;
  }

  renderShell(
    `${course.code}: ${formatDate(section.date)} office hours.`,
    `
      <button id="backToCourses" class="secondary-action back-button" type="button">Back to Courses</button>
      <section class="panel section-hero ${section.changeHighlighted ? "highlighted" : ""}">
        <div>
          <p class="eyebrow">${escapeHtml(course.code)}</p>
          <h3>${escapeHtml(course.title || course.code)}</h3>
          <p>${formatDate(section.date)} at ${formatTimeRange(section)} · ${escapeHtml(section.location || section.zoomLink || "Location TBD")}</p>
          ${renderSectionChanges(section)}
        </div>
        ${
          role === "ta"
            ? `<div class="share-panel">
                <button class="secondary-action" data-copy="${escapeHtml(shareUrl("student", section.studentShareCode, section.id))}" type="button">Share Section To Students</button>
                <button class="secondary-action" data-copy="${escapeHtml(shareUrl("ta", section.taShareCode, section.id))}" type="button">Share Section To TAs</button>
                <small>Student code: ${escapeHtml(section.studentShareCode)}</small>
                <small>TA code: ${escapeHtml(section.taShareCode)}</small>
              </div>`
            : ""
        }
      </section>
      ${role === "ta" ? renderTaSectionTools(course, section, state) : renderStudentSectionTools(course, section, state)}
    `
  );

  document.querySelector("#backToCourses").addEventListener("click", async () => {
    setActiveSection(null);
    if (returnCourseId) {
      const courseId = returnCourseId;
      returnCourseId = null;
      window.sessionStorage.removeItem(`${role}_return_course`);
      setActiveCourse(courseId);
      await renderCourseView(courseId);
      return;
    }
    await renderDashboard();
  });
  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      await copyText(button.dataset.copy);
      button.textContent = "Copied";
    });
  });
  bindSectionActionForms(course, section);
}

function renderTaSectionTools(course, section, state) {
  const current = state.staff.currentStudent;
  return `
    <section class="two-column">
      <article class="panel">
        <p class="panel-label">Course</p>
        <form id="courseEditForm" class="stack-form">
          <label>Course code<input name="code" type="text" value="${escapeHtml(course.code)}" /></label>
          <label>Title<input name="title" type="text" value="${escapeHtml(course.title || "")}" /></label>
          <button class="secondary-action" type="submit">Update Course</button>
        </form>
      </article>
      <article class="panel">
        <p class="panel-label">Section Details</p>
        ${renderEditSectionForm(section)}
      </article>
    </section>
    <section class="hero-grid">
      <article class="panel crowd-panel">
        <p class="panel-label">Current Crowd</p>
        <h3>${state.live.estimatedWaitMinutes} min wait</h3>
        <div class="metric-row">
          <div><p class="metric-label">Waiting</p><strong>${state.live.studentsWaiting}</strong></div>
          <div><p class="metric-label">TAs</p><strong>${state.live.tasActive}</strong></div>
          <div><p class="metric-label">Avg Help</p><strong>${state.live.averageHelpMinutes} min</strong></div>
        </div>
      </article>
      <article class="panel current-student">
        <p class="metric-label">Currently helping</p>
        <h3>${escapeHtml(current?.name || "No student called")}</h3>
        <p>${current ? escapeHtml(`${current.course} · ${current.need}`) : "Call the next student when ready."}</p>
        <div class="staff-actions">
          <button id="callNext" class="primary-action" type="button">Call Next</button>
          <button id="markServed" class="secondary-action" type="button">Mark Served</button>
        </div>
      </article>
    </section>
    <section class="panel">
      <div class="section-heading">
        <div><p class="eyebrow">Waiting Line</p><h3>Students waiting for help</h3></div>
        <span class="forecast-note">${state.staff.servedCount} served</span>
      </div>
      <div class="staff-queue-list">
        ${
          state.staff.waitingEntries.length
            ? state.staff.waitingEntries
                .map(
                  (entry) => `
                    <div class="staff-queue-item">
                      <span class="queue-position">${entry.position}</span>
                      <div>
                        <strong>${escapeHtml(entry.name)}</strong>
                        <span>${escapeHtml(entry.course)} · ${escapeHtml(entry.need)}</span>
                        <p class="student-question">${escapeHtml(entry.message || "No question details provided.")}</p>
                        <p class="ai-summary">${escapeHtml(entry.ai?.summary || "")}</p>
                      </div>
                      <span class="tag medium">${entry.ai?.estimatedHelpMinutes || 7} min</span>
                    </div>
                  `
                )
                .join("")
            : `<div class="empty-state">No students waiting.</div>`
        }
      </div>
    </section>
  `;
}

function renderStudentSectionTools(course, section, state) {
  const isInLine = state.queue.status !== "not_joined";
  return `
    <section class="hero-grid">
      <article class="panel">
        <div class="section-heading">
          <div><p class="eyebrow">Virtual Line</p><h3>${isInLine ? "You are in line" : "Join this section"}</h3></div>
          <span class="turn-badge">${escapeHtml(state.queue.status.replace("_", " "))}</span>
        </div>
        ${
          isInLine
            ? `
              <div class="queue-state">
                <div><p class="metric-label">Place</p><strong>${state.queue.status === "called" ? "Now" : state.queue.position || "-"}</strong></div>
                <div><p class="metric-label">Wait</p><strong>${state.queue.personalWaitMinutes || 0} min</strong></div>
                <button id="leaveLine" class="secondary-action" type="button">Leave Line</button>
              </div>`
            : `
              <form id="queueForm" class="queue-form">
                <label>Name<input name="name" type="text" value="${escapeHtml(currentUser?.name || "")}" required /></label>
                <label>Need<select name="need"><option>Debugging help</option><option>Concept question</option><option>Assignment review</option><option>Exam prep</option></select></label>
                <label>Question details<textarea name="message" rows="4" placeholder="What are you stuck on?"></textarea></label>
                <button class="primary-action" type="submit">Join Virtual Line</button>
              </form>`
        }
      </article>
      <article class="panel crowd-panel">
        <p class="panel-label">Current Crowd</p>
        <h3>${state.live.estimatedWaitMinutes} min wait</h3>
        <div class="metric-row">
          <div><p class="metric-label">Waiting</p><strong>${state.live.studentsWaiting}</strong></div>
          <div><p class="metric-label">TAs</p><strong>${state.live.tasActive}</strong></div>
          <div><p class="metric-label">Avg Help</p><strong>${state.live.averageHelpMinutes} min</strong></div>
        </div>
      </article>
    </section>
  `;
}

function bindSectionActionForms(course, section) {
  document.querySelector("#courseEditForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    await api(`/api/courses/${course.id}`, {
      method: "PATCH",
      body: { code: data.get("code"), title: data.get("title") },
    });
    await renderSectionView(section.id);
  });

  document.querySelectorAll("[data-edit-section-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = new FormData(event.currentTarget);
      await api(`/api/sections/${form.dataset.editSectionForm}`, {
        method: "PATCH",
        body: {
          date: data.get("date"),
          startTime: data.get("startTime"),
          endTime: data.get("endTime"),
          location: data.get("location"),
          zoomLink: data.get("zoomLink"),
          highlightChange: data.get("highlightChange") === "on",
        },
      });
      await renderSectionView(section.id);
    });
  });

  document.querySelector("#callNext")?.addEventListener("click", async () => {
    await api(`/api/staff/call-next?slot_id=${encodeURIComponent(section.id)}`, { method: "POST" });
    await renderSectionView(section.id);
  });

  document.querySelector("#markServed")?.addEventListener("click", async () => {
    await api(`/api/staff/serve-current?slot_id=${encodeURIComponent(section.id)}`, { method: "POST" });
    await renderSectionView(section.id);
  });

  document.querySelector("#queueForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const result = await api("/api/queue", {
      method: "POST",
      body: {
        slotId: section.id,
        course: course.code,
        name: data.get("name"),
        need: data.get("need"),
        message: data.get("message"),
      },
    });
    queueToken = result.queueToken;
    window.localStorage.setItem("studyline_queue_token", queueToken);
    await renderSectionView(section.id);
  });

  document.querySelector("#leaveLine")?.addEventListener("click", async () => {
    await api(`/api/queue/me?slot_id=${encodeURIComponent(section.id)}`, { method: "DELETE" });
    queueToken = null;
    window.localStorage.removeItem("studyline_queue_token");
    await renderSectionView(section.id);
  });
}

function updateClock() {
  const now = new Date();
  const clock = document.querySelector("#liveClockInline");
  if (clock) clock.textContent = now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  document.querySelectorAll("[data-calendar-date]").forEach((column) => {
    const marker = column.querySelector(".current-time-line");
    const minutes = now.getHours() * 60 + now.getMinutes();
    marker.hidden = column.dataset.calendarDate !== localDateKey(now) || minutes < Number(column.dataset.startHour) * 60 || minutes >= Number(column.dataset.endHour) * 60;
    marker.style.top = `${(minutes / 60 - Number(column.dataset.startHour)) * 64}px`;
    marker.title = `Current time: ${now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
  });
}

async function boot() {
  updateClock();
  setInterval(updateClock, 30 * 1000);
  if (!["student", "ta"].includes(role)) {
    return;
  }
  await loadGoogleConfig();
  if (!authToken) {
    renderLogin();
    return;
  }
  try {
    const session = await api("/api/auth/me");
    currentUser = session.user;
    window.localStorage.setItem(userKey, JSON.stringify(currentUser));
    await afterLogin();
  } catch {
    authToken = null;
    currentUser = null;
    window.localStorage.removeItem(tokenKey);
    window.localStorage.removeItem(userKey);
    renderLogin();
  }
}

boot().catch((error) => {
  renderShell("Something needs attention.", `<section class="panel form-error">${escapeHtml(error.message)}</section>`);
});
