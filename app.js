// Frontend data contract notes
// --------------------------------
// This file assumes a FastAPI backend is available and that the backend now
// exposes smaller, focused endpoints instead of one all-in-one state payload.
//
// Expected endpoints:
// - GET /api/slots
// - GET /api/slots/{slotId}/overview
// - GET /api/forecast?slot_id={slotId}
// - GET /api/queue/me?slot_id={slotId}
// - GET /api/student/sessions
// - GET /api/staff/queue?slot_id={slotId}
// - GET /api/staff/queue/{entryId}
// - POST /api/queue
// - DELETE /api/queue/me?slot_id={slotId}
// - POST /api/staff/call-next?slot_id={slotId}
// - POST /api/staff/serve-current?slot_id={slotId}
// - POST /api/simulate-crowd?slot_id={slotId}
//
// The UI is intentionally kept the same as the previous demo, but this version
// now composes page state on the client and stores server-issued tokens instead
// of treating a raw student id as an identity/session mechanism.

const STORAGE_KEYS = {
  queueToken: "oh_queue_token",
  sessionToken: "oh_session_token",
  selectedSlotId: "oh_selected_slot_id",
};

// Remove the legacy raw-student-id key so we do not keep using a fragile
// identifier once the backend is persistent and multi-user.
window.localStorage.removeItem("oh_student_id");

let appState = createEmptyState();
let queueToken = window.localStorage.getItem(STORAGE_KEYS.queueToken);
let sessionToken = window.localStorage.getItem(STORAGE_KEYS.sessionToken);
let selectedSlotId = window.localStorage.getItem(STORAGE_KEYS.selectedSlotId);
const entryDetailsCache = new Map();
const page = document.body.dataset.page;

const form = document.querySelector("#queueForm");
const queueState = document.querySelector("#queueState");
const turnBadge = document.querySelector("#turnBadge");
const placeInLine = document.querySelector("#placeInLine");
const personalWait = document.querySelector("#personalWait");
const studentsWaiting = document.querySelector("#studentsWaiting");
const tasActive = document.querySelector("#tasActive");
const helpTime = document.querySelector("#helpTime");
const waitNow = document.querySelector("#waitNow");
const crowdHeadline = document.querySelector("#crowdHeadline");
const crowdMeter = document.querySelector("#crowdMeter");
const recommendations = document.querySelector("#recommendations");
const forecastEl = document.querySelector("#forecast");
const notificationTitle = document.querySelector("#notificationTitle");
const notificationBody = document.querySelector("#notificationBody");
const currentStudentName = document.querySelector("#currentStudentName");
const currentStudentNeed = document.querySelector("#currentStudentNeed");
const staffQueueList = document.querySelector("#staffQueueList");
const servedCount = document.querySelector("#servedCount");
const callNext = document.querySelector("#callNext");
const markServed = document.querySelector("#markServed");
const studentSlotCalendar = document.querySelector("#studentSlotCalendar");
const selectedSlotLabel = document.querySelector("#selectedSlotLabel");
const availabilityForm = document.querySelector("#availabilityForm");
const taSlotList = document.querySelector("#taSlotList");
const joinedSessionsList = document.querySelector("#joinedSessionsList");
const liveClock = document.querySelector("#liveClock");

function createEmptyState() {
  return {
    slots: [],
    live: {
      studentsWaiting: 0,
      tasActive: 0,
      averageHelpMinutes: 0,
      estimatedWaitMinutes: 0,
    },
    queue: {
      status: "not_joined",
      position: null,
      personalWaitMinutes: null,
      entryId: null,
    },
    staff: {
      currentStudent: null,
      waitingEntries: [],
      servedCount: 0,
    },
    sessions: [],
    forecast: [],
  };
}

function crowdLabel(wait) {
  if (wait <= 10) return { label: "Light", className: "low", color: "#15845c", width: "28%" };
  if (wait <= 22) return { label: "Moderate", className: "medium", color: "#b86b00", width: "58%" };
  return { label: "Very Busy", className: "high", color: "#b33b33", width: "88%" };
}

function crowdFromLevel(level) {
  if (level <= 35) return "low";
  if (level <= 65) return "medium";
  return "high";
}

function ordinal(value) {
  const suffix = value === 1 ? "st" : value === 2 ? "nd" : value === 3 ? "rd" : "th";
  return `${value}${suffix}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function readField(source, ...keys) {
  for (const key of keys) {
    if (source && source[key] !== undefined && source[key] !== null) {
      return source[key];
    }
  }

  return null;
}

function normalizeArray(value) {
  return Array.isArray(value) ? value : [];
}

function persistSelectedSlotId(nextSlotId) {
  selectedSlotId = nextSlotId || null;

  if (selectedSlotId) {
    window.localStorage.setItem(STORAGE_KEYS.selectedSlotId, selectedSlotId);
  } else {
    window.localStorage.removeItem(STORAGE_KEYS.selectedSlotId);
  }
}

function persistTokens(payload = {}) {
  const nextQueueToken = readField(payload, "queueToken", "queue_token");
  const nextSessionToken = readField(payload, "sessionToken", "session_token");

  if (nextQueueToken) {
    queueToken = nextQueueToken;
    window.localStorage.setItem(STORAGE_KEYS.queueToken, queueToken);
  }

  if (nextSessionToken) {
    sessionToken = nextSessionToken;
    window.localStorage.setItem(STORAGE_KEYS.sessionToken, sessionToken);
  }
}

function clearQueueToken() {
  queueToken = null;
  window.localStorage.removeItem(STORAGE_KEYS.queueToken);
}

function authHeaders() {
  const headers = {};

  if (sessionToken) {
    headers["X-Session-Token"] = sessionToken;
  }

  if (queueToken) {
    headers["X-Queue-Token"] = queueToken;
  }

  return headers;
}

// Centralized request helper so every route consistently sends session tokens
// and surfaces backend error messages when FastAPI returns structured errors.
async function api(path, options = {}) {
  const query = options.query ? `?${new URLSearchParams(options.query).toString()}` : "";
  const response = await fetch(`${path}${query}`, {
    method: options.method || "GET",
    headers: {
      ...authHeaders(),
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  const rawText = await response.text();
  let data = {};

  if (rawText) {
    try {
      data = JSON.parse(rawText);
    } catch {
      data = { message: rawText };
    }
  }

  persistTokens(data);

  if (!response.ok) {
    throw new Error(readField(data, "detail", "error", "message") || `Request failed: ${response.status}`);
  }

  return data;
}

function normalizeSlot(slot) {
  return {
    id: readField(slot, "id"),
    date: readField(slot, "date"),
    startTime: readField(slot, "startTime", "start_time"),
    endTime: readField(slot, "endTime", "end_time"),
    taName: readField(slot, "taName", "ta_name") || "TA",
    location: readField(slot, "location") || "Office Hours Room",
    studentsWaiting: Number(readField(slot, "studentsWaiting", "students_waiting") || 0),
    estimatedWaitMinutes: Number(readField(slot, "estimatedWaitMinutes", "estimated_wait_minutes") || 0),
    crowd: readField(slot, "crowd") || crowdLabel(Number(readField(slot, "estimatedWaitMinutes", "estimated_wait_minutes") || 0)).className,
  };
}

function normalizeLiveOverview(data) {
  return {
    studentsWaiting: Number(readField(data, "studentsWaiting", "students_waiting") || 0),
    tasActive: Number(readField(data, "tasActive", "tas_active") || 0),
    averageHelpMinutes: Number(readField(data, "averageHelpMinutes", "average_help_minutes") || 0),
    estimatedWaitMinutes: Number(readField(data, "estimatedWaitMinutes", "estimated_wait_minutes") || 0),
  };
}

function normalizeQueueStatus(data) {
  const status = readField(data, "status") || "not_joined";
  const estimatedWait = Number(readField(data, "personalWaitMinutes", "personal_wait_minutes", "estimatedWaitMinutes", "estimated_wait_minutes") || 0);

  return {
    status,
    position: readField(data, "position") ? Number(readField(data, "position")) : null,
    personalWaitMinutes: status === "not_joined" ? null : estimatedWait,
    entryId: readField(data, "entryId", "entry_id"),
    slotId: readField(data, "slotId", "slot_id"),
  };
}

function normalizeForecast(forecast) {
  return normalizeArray(forecast).map((slot) => {
    const level = Number(readField(slot, "level") || 0);
    return {
      time: readField(slot, "time") || "--",
      level,
      crowd: readField(slot, "crowd") || crowdFromLevel(level),
    };
  });
}

function normalizeStudentSession(session) {
  return {
    id: readField(session, "id"),
    studentId: readField(session, "studentId", "student_id"),
    slotId: readField(session, "slotId", "slot_id"),
    slotLabel: buildSlotSummary(session),
    course: readField(session, "course") || "General",
    need: readField(session, "need") || "Office hours help",
    status: readField(session, "status") || "waiting",
    waitText: buildSessionWaitText(session),
    joinedAt: formatDateTime(readField(session, "joinedAt", "joined_at")),
  };
}

function normalizeStaffQueueSummary(data) {
  return {
    servedCount: Number(readField(data, "servedCount", "served_count") || 0),
    currentStudentId: readField(data, "currentStudentId", "current_student_id"),
    waitingEntries: normalizeArray(readField(data, "waitingEntries", "waiting_entries")).map((entry) => ({
      id: readField(entry, "id"),
      name: readField(entry, "name") || "Student",
      course: readField(entry, "course") || "General",
      need: readField(entry, "need") || "Office hours help",
      position: Number(readField(entry, "position") || 0),
      estimatedHelpMinutes: Number(readField(entry, "estimatedHelpMinutes", "estimated_help_minutes") || 0),
    })),
  };
}

function normalizeEntryDetail(entry) {
  if (!entry) {
    return null;
  }

  const ai = readField(entry, "ai") || {};
  return {
    id: readField(entry, "id"),
    name: readField(entry, "name") || "Student",
    course: readField(entry, "course") || "General",
    need: readField(entry, "need") || "Office hours help",
    message: readField(entry, "message") || "",
    file: readField(entry, "file"),
    status: readField(entry, "status") || "waiting",
    ai: {
      summary: readField(ai, "summary") || "Student needs office hours support.",
      estimatedHelpMinutes: Number(readField(ai, "estimatedHelpMinutes", "estimated_help_minutes") || 0),
      source: readField(ai, "source") || "unknown",
      model: readField(ai, "model"),
    },
  };
}

function buildSlotSummary(source) {
  const date = readField(source, "date");
  const startTime = readField(source, "startTime", "start_time");
  const endTime = readField(source, "endTime", "end_time");

  if (!date || !startTime || !endTime) {
    return "Selected office-hour slot";
  }

  return `${date}, ${formatTimeRange(startTime, endTime)}`;
}

function buildSessionWaitText(session) {
  const waitMinutes = readField(session, "waitMinutes", "wait_minutes", "estimatedWaitMinutes", "estimated_wait_minutes");
  return waitMinutes ? `${waitMinutes} min wait` : "wait unavailable";
}

function formatDateTime(value) {
  if (!value) {
    return "Unknown time";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return String(value);
  }

  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatTimeLabel(time) {
  const [hourText = "0", minute = "00"] = String(time || "").split(":");
  const hour = Number(hourText);
  const suffix = hour >= 12 ? "PM" : "AM";
  const displayHour = hour % 12 || 12;
  return `${displayHour}:${minute} ${suffix}`;
}

function formatTimeRange(startTime, endTime) {
  return `${formatTimeLabel(startTime)} - ${formatTimeLabel(endTime)}`;
}

function formatAiSource(ai) {
  if (!ai) {
    return "unknown";
  }

  if (ai.source === "gemini") {
    return ai.model ? `Gemini (${ai.model})` : "Gemini";
  }

  if (ai.source === "simulation") {
    return "simulation";
  }

  return "local fallback";
}

function getSelectedSlotText() {
  const slot = appState.slots.find((item) => item.id === selectedSlotId);
  return slot ? `${slot.date}, ${formatTimeRange(slot.startTime, slot.endTime)} with ${slot.taName}` : "No slot selected";
}

function getRecommendedSlots() {
  return [...appState.slots].sort((left, right) => left.estimatedWaitMinutes - right.estimatedWaitMinutes);
}

async function fetchSlots() {
  const data = await api("/api/slots");
  return normalizeArray(readField(data, "slots")).map(normalizeSlot);
}

async function fetchLiveOverview(slotId) {
  if (!slotId) {
    return createEmptyState().live;
  }

  const data = await api(`/api/slots/${encodeURIComponent(slotId)}/overview`);
  return normalizeLiveOverview(data);
}

async function fetchQueueStatus(slotId) {
  if (!slotId || !queueToken) {
    return createEmptyState().queue;
  }

  try {
    const data = await api("/api/queue/me", {
      query: { slot_id: slotId },
    });

    const status = normalizeQueueStatus(data);

    if (status.status === "not_joined") {
      clearQueueToken();
    }

    return status;
  } catch (error) {
    clearQueueToken();
    return createEmptyState().queue;
  }
}

async function fetchStudentSessions() {
  if (!sessionToken) {
    return [];
  }

  const data = await api("/api/student/sessions");
  return normalizeArray(readField(data, "sessions")).map(normalizeStudentSession);
}

async function fetchForecast(slotId) {
  if (!slotId) {
    return [];
  }

  const data = await api("/api/forecast", {
    query: { slot_id: slotId },
  });

  return normalizeForecast(readField(data, "forecast"));
}

async function fetchStaffQueueSummary(slotId) {
  if (!slotId) {
    return createEmptyState().staff;
  }

  const data = await api("/api/staff/queue", {
    query: { slot_id: slotId },
  });

  return normalizeStaffQueueSummary(data);
}

async function fetchEntryDetail(entryId) {
  if (!entryId) {
    return null;
  }

  if (!entryDetailsCache.has(entryId)) {
    const request = api(`/api/staff/queue/${encodeURIComponent(entryId)}`).then(normalizeEntryDetail);
    entryDetailsCache.set(entryId, request);
  }

  return entryDetailsCache.get(entryId);
}

// The staff page intentionally pulls a lightweight queue list first and then
// fetches detailed question/AI payloads per entry so large queues do not force
// a huge embedded response for every poll.
async function buildStaffState(slotId) {
  const summary = await fetchStaffQueueSummary(slotId);
  const detailIds = [
    summary.currentStudentId,
    ...summary.waitingEntries.map((entry) => entry.id),
  ].filter(Boolean);

  await Promise.all(detailIds.map((entryId) => fetchEntryDetail(entryId)));

  const waitingEntries = await Promise.all(
    summary.waitingEntries.map(async (entry) => {
      const detail = await fetchEntryDetail(entry.id);
      return {
        ...entry,
        ...detail,
        ai: {
          ...(detail?.ai || {}),
          estimatedHelpMinutes: entry.estimatedHelpMinutes || detail?.ai?.estimatedHelpMinutes || 0,
        },
      };
    })
  );

  const currentStudent = summary.currentStudentId ? await fetchEntryDetail(summary.currentStudentId) : null;

  return {
    currentStudent,
    waitingEntries,
    servedCount: summary.servedCount,
  };
}

function reconcileSelectedSlot(slots) {
  if (!slots.length) {
    persistSelectedSlotId(null);
    return;
  }

  const hasCurrentSelection = selectedSlotId && slots.some((slot) => slot.id === selectedSlotId);
  if (!hasCurrentSelection) {
    persistSelectedSlotId(slots[0].id);
  }
}

async function loadState() {
  const slots = await fetchSlots();
  reconcileSelectedSlot(slots);
  const slotId = selectedSlotId;

  const livePromise = fetchLiveOverview(slotId);
  const queuePromise = fetchQueueStatus(slotId);
  const forecastPromise = fetchForecast(slotId);
  const sessionsPromise = page === "student" ? fetchStudentSessions() : Promise.resolve([]);
  const staffPromise = page === "ta" ? buildStaffState(slotId) : Promise.resolve(createEmptyState().staff);

  const [live, queue, forecast, sessions, staff] = await Promise.all([
    livePromise,
    queuePromise,
    forecastPromise,
    sessionsPromise,
    staffPromise,
  ]);

  renderAll({
    slots,
    live,
    queue,
    forecast,
    sessions,
    staff,
  });
}

function renderAll(nextState) {
  appState = nextState;
  renderSlots();
  renderLiveData();
  renderRecommendations();
  renderForecast();
  renderStaffDashboard();
  renderJoinedSessions();
}

function renderLiveData() {
  if (!studentsWaiting || !tasActive || !helpTime || !waitNow || !crowdHeadline || !crowdMeter) {
    return;
  }

  const wait = appState.live.estimatedWaitMinutes;
  const crowd = crowdLabel(wait);
  studentsWaiting.textContent = appState.live.studentsWaiting;
  tasActive.textContent = appState.live.tasActive;
  helpTime.textContent = `${appState.live.averageHelpMinutes} min`;
  waitNow.textContent = `${wait} min`;
  crowdHeadline.textContent = crowd.label;
  crowdMeter.style.width = crowd.width;
  crowdMeter.style.background = crowd.color;

  if (!queueState || !turnBadge || !placeInLine || !personalWait) {
    return;
  }

  if (appState.queue.status === "called") {
    placeInLine.textContent = "Now";
    personalWait.textContent = "0 min";
    queueState.classList.remove("hidden");
    turnBadge.textContent = "Go to TA";
  } else if (appState.queue.position) {
    const place = appState.queue.position;
    placeInLine.textContent = ordinal(place);
    personalWait.textContent = `${appState.queue.personalWaitMinutes} min`;
    queueState.classList.remove("hidden");
    turnBadge.textContent = place === 1 ? "Your turn soon" : "In line";
  } else {
    queueState.classList.add("hidden");
    turnBadge.textContent = "Not in line";
  }
}

function renderStaffDashboard() {
  if (!currentStudentName || !currentStudentNeed || !staffQueueList || !servedCount) {
    return;
  }

  const current = appState.staff.currentStudent;
  servedCount.textContent = `${appState.staff.servedCount} served`;

  if (current) {
    currentStudentName.textContent = current.name;
    currentStudentNeed.innerHTML = `
      <span>${current.course} - ${current.need} - ${current.ai.estimatedHelpMinutes} min estimate</span>
      <strong>Question</strong>
      <span>${escapeHtml(current.message || "No question details provided.")}</span>
      <strong>AI summary</strong>
      <span>${escapeHtml(current.ai.summary)}</span>
      ${current.file ? `<span class="file-chip">Attachment: ${escapeHtml(current.file.name)}</span>` : ""}
    `;
  } else {
    currentStudentName.textContent = "No student called";
    currentStudentNeed.textContent = "Call the next student when a TA is ready.";
  }

  if (!appState.staff.waitingEntries.length) {
    staffQueueList.innerHTML = `<div class="empty-state">No students waiting.</div>`;
    return;
  }

  staffQueueList.innerHTML = appState.staff.waitingEntries
    .map(
      (entry) => `
        <div class="staff-queue-item">
          <span class="queue-position">${entry.position}</span>
          <div>
            <strong>${escapeHtml(entry.name)}</strong>
            <span>${escapeHtml(entry.course)} - ${escapeHtml(entry.need)}</span>
            <p class="student-question"><strong>Question:</strong> ${escapeHtml(entry.message || "No question details provided.")}</p>
            <p class="ai-summary">${escapeHtml(entry.ai.summary || "No AI summary available.")}</p>
            <p class="ai-source">AI source: ${formatAiSource(entry.ai)}</p>
            ${entry.file ? `<p class="file-chip">Attachment: ${escapeHtml(entry.file.name)}</p>` : ""}
          </div>
          <span class="tag ${entry.position === 1 ? "low" : "medium"}">${entry.ai.estimatedHelpMinutes} min help</span>
        </div>
      `
    )
    .join("");
}

function renderSlots() {
  if (!appState.slots.length) {
    if (studentSlotCalendar) {
      studentSlotCalendar.innerHTML = `<div class="empty-state">No TA times available yet.</div>`;
    }

    if (taSlotList) {
      taSlotList.innerHTML = `<div class="empty-state">Add your first office-hour block above.</div>`;
    }

    if (selectedSlotLabel) {
      selectedSlotLabel.textContent = "Select a time slot to join.";
    }

    return;
  }

  if (studentSlotCalendar) {
    studentSlotCalendar.innerHTML = appState.slots.map(renderSlotButton).join("");
    selectedSlotLabel.textContent = `Selected: ${getSelectedSlotText()}`;
  }

  if (taSlotList) {
    taSlotList.innerHTML = appState.slots.map(renderSlotButton).join("");
  }
}

function renderSlotButton(slot) {
  const isSelected = slot.id === selectedSlotId;
  const removeButton =
    page === "ta"
      ? `<button class="slot-remove" type="button" data-remove-slot-id="${slot.id}" aria-label="Remove ${formatTimeRange(slot.startTime, slot.endTime)}">Remove</button>`
      : "";

  return `
    <button class="slot-button ${isSelected ? "selected" : ""}" type="button" data-slot-id="${slot.id}">
      <strong>${escapeHtml(slot.date)}</strong>
      <span>${escapeHtml(formatTimeRange(slot.startTime, slot.endTime))}</span>
      <span>${escapeHtml(slot.taName)} - ${escapeHtml(slot.location)}</span>
      <small>${slot.studentsWaiting} waiting - ${slot.estimatedWaitMinutes} min</small>
      ${removeButton}
    </button>
  `;
}

function renderRecommendations() {
  if (!recommendations) {
    return;
  }

  recommendations.innerHTML = getRecommendedSlots()
    .map(
      (slot) => `
        <div class="recommendation">
          <div>
            <strong>${escapeHtml(formatTimeRange(slot.startTime, slot.endTime))} - ${escapeHtml(slot.location)}</strong>
            <span>${escapeHtml(slot.taName)} available</span>
          </div>
          <span class="tag ${slot.crowd}">${slot.estimatedWaitMinutes} min</span>
        </div>
      `
    )
    .join("");
}

function renderForecast() {
  if (!forecastEl) {
    return;
  }

  forecastEl.innerHTML = appState.forecast
    .map(
      (slot) => `
        <div class="forecast-row">
          <div>
            <strong>${escapeHtml(slot.time)}</strong>
            <div class="bar"><span class="tag ${slot.crowd}" style="width: ${slot.level}%"></span></div>
          </div>
          <span class="tag ${slot.crowd}">${escapeHtml(slot.crowd)}</span>
        </div>
      `
    )
    .join("");
}

function renderJoinedSessions() {
  if (!joinedSessionsList) {
    return;
  }

  if (!appState.sessions.length) {
    joinedSessionsList.innerHTML = `<div class="empty-state">No joined sessions yet.</div>`;
    return;
  }

  joinedSessionsList.innerHTML = appState.sessions
    .map((session) => {
      const isActive = session.slotId === selectedSlotId && appState.queue.status !== "not_joined";
      const status = isActive && appState.queue.status ? appState.queue.status.replace("_", " ") : session.status;
      const wait = isActive && appState.queue.personalWaitMinutes ? `${appState.queue.personalWaitMinutes} min wait` : session.waitText;

      return `
        <div class="joined-session ${isActive ? "active" : ""}">
          <div>
            <strong>${escapeHtml(session.slotLabel)}</strong>
            <span>${escapeHtml(session.course)} - ${escapeHtml(session.need)}</span>
            <small>${escapeHtml(session.joinedAt)}</small>
          </div>
          <span class="tag ${isActive ? "low" : "medium"}">${escapeHtml(status)} / ${escapeHtml(wait)}</span>
        </div>
      `;
    })
    .join("");
}

function updateLiveClock() {
  if (!liveClock) {
    return;
  }

  liveClock.textContent = new Date().toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

function setJoinLoading(isLoading, submitButton) {
  if (!submitButton) {
    return;
  }

  submitButton.disabled = isLoading;
  submitButton.classList.toggle("loading", isLoading);
  submitButton.textContent = isLoading ? "Joining..." : "Join Virtual Line";

  if (notificationTitle && notificationBody && isLoading) {
    notificationTitle.innerHTML = `<span class="loading-dots"><i></i><i></i><i></i></span>Joining your selected slot`;
    notificationBody.textContent = "The backend is saving your session and estimating help time. This may take a few seconds.";
  }
}

// The frontend now uploads real file contents so the Python backend can support
// future code review and attachment-based features instead of metadata only.
async function buildQueuePayload() {
  const fileInput = document.querySelector("#questionFile");
  const file = fileInput?.files?.[0];
  const attachment = file
    ? {
        name: file.name,
        type: file.type || "unknown",
        size: file.size,
        contentBase64: await fileToBase64(file),
      }
    : null;

  return {
    name: document.querySelector("#studentName").value,
    course: document.querySelector("#courseSelect").value,
    need: document.querySelector("#needSelect").value,
    message: document.querySelector("#questionMessage").value,
    slot_id: selectedSlotId,
    attachment,
  };
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      resolve(result.includes(",") ? result.split(",")[1] : result);
    };
    reader.onerror = () => reject(reader.error || new Error("Could not read file"));
    reader.readAsDataURL(file);
  });
}

async function refreshAfterMutation() {
  entryDetailsCache.clear();
  await loadState();
}

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submitButton = form.querySelector("button[type='submit']");
  setJoinLoading(true, submitButton);

  try {
    const result = await api("/api/queue", {
      method: "POST",
      body: await buildQueuePayload(),
    });

    persistTokens(result);
    notificationTitle.textContent = "You joined the virtual line.";
    notificationBody.textContent = "Keep your spot while you finish what you are doing. We will notify you before your turn.";
    await refreshAfterMutation();
  } catch (error) {
    notificationTitle.textContent = "Could not join the line.";
    notificationBody.textContent = error.message || "Please try again in a moment.";
  } finally {
    setJoinLoading(false, submitButton);
  }
});

document.querySelector("#leaveLine")?.addEventListener("click", async () => {
  if (queueToken) {
    await api("/api/queue/me", {
      method: "DELETE",
      query: { slot_id: selectedSlotId || "" },
    });
  }

  clearQueueToken();
  notificationTitle.textContent = "You left the queue.";
  notificationBody.textContent = "Check the recommendations to pick a less crowded time.";
  await refreshAfterMutation();
});

document.querySelector("#refreshData")?.addEventListener("click", async () => {
  await api("/api/simulate-crowd", {
    method: "POST",
    query: { slot_id: selectedSlotId || "" },
  });
  await refreshAfterMutation();
});

document.querySelector("#simulateTurn")?.addEventListener("click", async () => {
  if (!queueToken) {
    notificationTitle.textContent = "Join the line first.";
    notificationBody.textContent = "Once you are in the queue, this alert tells you when to head over.";
    return;
  }

  while (appState.queue.position && appState.queue.position > 1) {
    await api("/api/staff/call-next", {
      method: "POST",
      query: { slot_id: selectedSlotId || "" },
    });
    await refreshAfterMutation();
  }

  if (appState.queue.position === 1) {
    await api("/api/staff/call-next", {
      method: "POST",
      query: { slot_id: selectedSlotId || "" },
    });
    await refreshAfterMutation();
  }

  notificationTitle.textContent = "You have been called.";
  notificationBody.textContent = "Please go to the TA now. Your virtual spot is being held.";
});

callNext?.addEventListener("click", async () => {
  await api("/api/staff/call-next", {
    method: "POST",
    query: { slot_id: selectedSlotId || "" },
  });
  await refreshAfterMutation();
});

markServed?.addEventListener("click", async () => {
  const result = await api("/api/staff/serve-current", {
    method: "POST",
    query: { slot_id: selectedSlotId || "" },
  });

  if (queueToken && readField(result, "served", "served_entry")) {
    const served = normalizeEntryDetail(readField(result, "served", "served_entry"));
    if (served?.id && served.id === appState.queue.entryId) {
      clearQueueToken();
      notificationTitle.textContent = "Your office hours visit is complete.";
      notificationBody.textContent = "Thanks for checking in. You can join again if you need more help.";
    }
  }

  await refreshAfterMutation();
});

document.addEventListener("click", async (event) => {
  const removeButton = event.target.closest("[data-remove-slot-id]");

  if (removeButton) {
    event.stopPropagation();
    const slotId = removeButton.dataset.removeSlotId;
    await api(`/api/availability/${encodeURIComponent(slotId)}`, { method: "DELETE" });

    if (selectedSlotId === slotId) {
      persistSelectedSlotId(null);
    }

    await refreshAfterMutation();
    return;
  }

  const slotButton = event.target.closest("[data-slot-id]");

  if (!slotButton) {
    return;
  }

  persistSelectedSlotId(slotButton.dataset.slotId);
  await loadState();
});

availabilityForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  await api("/api/availability", {
    method: "POST",
    body: {
      date: document.querySelector("#availabilityDate").value,
      start_time: document.querySelector("#availabilityStart").value,
      end_time: document.querySelector("#availabilityEnd").value,
      location: document.querySelector("#availabilityLocation").value,
      ta_name: "Bobby",
    },
  });

  await refreshAfterMutation();
});

function setDefaultAvailabilityDate() {
  const dateInput = document.querySelector("#availabilityDate");

  if (dateInput && !dateInput.value) {
    dateInput.value = new Date().toISOString().slice(0, 10);
  }
}

if (page === "student" || page === "ta") {
  updateLiveClock();
  setInterval(updateLiveClock, 30 * 1000);
  setDefaultAvailabilityDate();
  loadState().catch(() => {
    if (notificationTitle && notificationBody) {
      notificationTitle.textContent = "Backend is not running.";
      notificationBody.textContent = "Start the FastAPI backend, then refresh this page.";
    }
  });
}
