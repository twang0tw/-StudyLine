let appState = null;
let studentId = window.localStorage.getItem("oh_student_id");
let selectedSlotId = window.localStorage.getItem("oh_selected_slot_id");
let joinedSessions = JSON.parse(window.localStorage.getItem("oh_joined_sessions") || "[]");
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

function crowdLabel(wait) {
  if (wait <= 10) return { label: "Light", className: "low", color: "#15845c", width: "28%" };
  if (wait <= 22) return { label: "Moderate", className: "medium", color: "#b86b00", width: "58%" };
  return { label: "Very Busy", className: "high", color: "#b33b33", width: "88%" };
}

function ordinal(value) {
  const suffix = value === 1 ? "st" : value === 2 ? "nd" : value === 3 ? "rd" : "th";
  return `${value}${suffix}`;
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
            <strong>${entry.name}</strong>
            <span>${entry.course} - ${entry.need}</span>
            <p class="student-question"><strong>Question:</strong> ${escapeHtml(entry.message || "No question details provided.")}</p>
            <p class="ai-summary">${entry.ai.summary}</p>
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
  if (!appState.slots?.length) {
    if (studentSlotCalendar) {
      studentSlotCalendar.innerHTML = `<div class="empty-state">No TA times available yet.</div>`;
    }

    if (taSlotList) {
      taSlotList.innerHTML = `<div class="empty-state">Add your first office-hour block above.</div>`;
    }

    return;
  }

  if (!selectedSlotId || !appState.slots.some((slot) => slot.id === selectedSlotId)) {
    selectedSlotId = appState.selectedSlotId || appState.slots[0].id;
    window.localStorage.setItem("oh_selected_slot_id", selectedSlotId);
  }

  if (studentSlotCalendar) {
    studentSlotCalendar.innerHTML = appState.slots.map(renderSlotButton).join("");
    selectedSlotLabel.textContent = `Selected: ${getSelectedSlotText()}`;
  }

  if (taSlotList) {
    taSlotList.innerHTML = appState.slots.map(renderSlotButton).join("");
  }
}

function renderJoinedSessions() {
  if (!joinedSessionsList) {
    return;
  }

  if (!joinedSessions.length) {
    joinedSessionsList.innerHTML = `<div class="empty-state">No joined sessions yet.</div>`;
    return;
  }

  joinedSessionsList.innerHTML = joinedSessions
    .map((session) => {
      const isActive = session.studentId === studentId;
      const status = isActive && appState?.queue?.status ? appState.queue.status.replace("_", " ") : session.status;
      const wait = isActive && appState?.queue?.personalWaitMinutes ? `${appState.queue.personalWaitMinutes} min wait` : session.waitText;

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

function renderSlotButton(slot) {
  const isSelected = slot.id === selectedSlotId;
  const removeButton =
    page === "ta"
      ? `<button class="slot-remove" type="button" data-remove-slot-id="${slot.id}" aria-label="Remove ${slot.label}">Remove</button>`
      : "";

  return `
    <button class="slot-button ${isSelected ? "selected" : ""}" type="button" data-slot-id="${slot.id}">
      <strong>${slot.date}</strong>
      <span>${slot.label}</span>
      <span>${slot.taName} - ${slot.location}</span>
      <small>${slot.studentsWaiting} waiting - ${slot.estimatedWaitMinutes} min</small>
      ${removeButton}
    </button>
  `;
}

function getSelectedSlotText() {
  const slot = appState.slots.find((item) => item.id === selectedSlotId);
  return slot ? `${slot.date}, ${slot.label} with ${slot.taName}` : "No slot selected";
}

function formatAiSource(ai) {
  if (!ai) {
    return "unknown";
  }

  if (ai.source === "gemini") {
    return ai.model ? `Gemini (${ai.model})` : "Gemini";
  }

  return "local fallback";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderRecommendations() {
  if (!recommendations) {
    return;
  }

  recommendations.innerHTML = appState.sessions
    .map(
      (session) => `
        <div class="recommendation">
          <div>
            <strong>${session.time} - ${session.room}</strong>
            <span>${session.note}</span>
          </div>
          <span class="tag ${session.crowd}">${session.wait} min</span>
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
            <strong>${slot.time}</strong>
            <div class="bar"><span class="tag ${slot.crowd}" style="width: ${slot.level}%"></span></div>
          </div>
          <span class="tag ${slot.crowd}">${slot.crowd}</span>
        </div>
      `
    )
    .join("");
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json();
}

function renderAll(nextState) {
  appState = nextState;
  selectedSlotId = nextState.selectedSlotId || selectedSlotId;
  if (selectedSlotId) {
    window.localStorage.setItem("oh_selected_slot_id", selectedSlotId);
  }
  renderSlots();
  renderLiveData();
  renderRecommendations();
  renderForecast();
  renderStaffDashboard();
  renderJoinedSessions();
}

async function loadState() {
  const params = new URLSearchParams();

  if (page === "student" && studentId) {
    params.set("studentId", studentId);
  }

  if (selectedSlotId) {
    params.set("slotId", selectedSlotId);
  }

  const query = params.toString() ? `?${params}` : "";
  renderAll(await api(`/api/state${query}`));
}

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submitButton = form.querySelector("button[type='submit']");
  const payload = {
    name: document.querySelector("#studentName").value,
    course: document.querySelector("#courseSelect").value,
    need: document.querySelector("#needSelect").value,
    message: document.querySelector("#questionMessage").value,
    file: getSelectedFileMetadata(),
    slotId: selectedSlotId,
  };

  setJoinLoading(true, submitButton);

  try {
    const result = await api("/api/queue", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    studentId = result.entry.id;
    window.localStorage.setItem("oh_student_id", studentId);
    saveJoinedSession(result.entry, result.state);
    notificationTitle.textContent = "You joined the virtual line.";
    notificationBody.textContent = "Keep your spot while you finish what you are doing. We will notify you before your turn.";
    renderAll(result.state);
  } catch (error) {
    notificationTitle.textContent = "Could not join the line.";
    notificationBody.textContent = error.message || "Please try again in a moment.";
  } finally {
    setJoinLoading(false, submitButton);
  }
});

function saveJoinedSession(entry, state) {
  const slot = state.slots.find((item) => item.id === entry.slotId);
  const record = {
    studentId: entry.id,
    slotId: entry.slotId,
    slotLabel: slot ? `${slot.date}, ${slot.label}` : "Selected office-hour slot",
    course: entry.course,
    need: entry.need,
    status: "waiting",
    waitText: `${state.queue.personalWaitMinutes || state.live.estimatedWaitMinutes} min wait`,
    joinedAt: new Date(entry.joinedAt).toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    }),
  };

  joinedSessions = [record, ...joinedSessions.filter((session) => session.studentId !== entry.id)].slice(0, 8);
  window.localStorage.setItem("oh_joined_sessions", JSON.stringify(joinedSessions));
  renderJoinedSessions();
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
    notificationBody.textContent = "Gemini is summarizing your question and estimating help time. This may take a few seconds.";
  }
}

function getSelectedFileMetadata() {
  const fileInput = document.querySelector("#questionFile");
  const file = fileInput?.files?.[0];

  if (!file) {
    return null;
  }

  return {
    name: file.name,
    type: file.type || "unknown",
    size: file.size,
  };
}

document.querySelector("#leaveLine")?.addEventListener("click", async () => {
  const leavingStudentId = studentId;

  if (studentId) {
    await api(`/api/queue/${studentId}${buildStateQuery()}`, { method: "DELETE" });
  }

  studentId = null;
  window.localStorage.removeItem("oh_student_id");
  joinedSessions = joinedSessions.map((session) =>
    session.studentId === leavingStudentId ? { ...session, status: "left", waitText: "left queue" } : session
  );
  window.localStorage.setItem("oh_joined_sessions", JSON.stringify(joinedSessions));
  notificationTitle.textContent = "You left the queue.";
  notificationBody.textContent = "Check the recommendations to pick a less crowded time.";
  await loadState();
});

document.querySelector("#refreshData")?.addEventListener("click", async () => {
  const query = buildStateQuery();
  renderAll(await api(`/api/simulate-crowd${query}`, { method: "POST" }));
});

document.querySelector("#simulateTurn")?.addEventListener("click", async () => {
  if (!studentId) {
    notificationTitle.textContent = "Join the line first.";
    notificationBody.textContent = "Once you are in the queue, this alert tells you when to head over.";
    return;
  }

  while (appState.queue.position && appState.queue.position > 1) {
    await api(`/api/staff/call-next${buildStateQuery()}`, { method: "POST" });
    await loadState();
  }

  if (appState.queue.position === 1) {
    await api(`/api/staff/call-next${buildStateQuery()}`, { method: "POST" });
    await loadState();
  }

  notificationTitle.textContent = "You have been called.";
  notificationBody.textContent = "Please go to the TA now. Your virtual spot is being held.";
});

callNext?.addEventListener("click", async () => {
  const query = buildStateQuery();
  const result = await api(`/api/staff/call-next${query}`, { method: "POST" });
  renderAll(result.state);

  if (page === "student" && result.next && result.next.id === studentId) {
    notificationTitle.textContent = "You have been called.";
    notificationBody.textContent = "Please go to the TA now. Your virtual spot is being held.";
  }
});

markServed?.addEventListener("click", async () => {
  const query = buildStateQuery();
  const result = await api(`/api/staff/serve-current${query}`, { method: "POST" });
  renderAll(result.state);

  if (page === "student" && result.served && result.served.id === studentId) {
    studentId = null;
    window.localStorage.removeItem("oh_student_id");
    notificationTitle.textContent = "Your office hours visit is complete.";
    notificationBody.textContent = "Thanks for checking in. You can join again if you need more help.";
    await loadState();
  }
});

document.addEventListener("click", async (event) => {
  const removeButton = event.target.closest("[data-remove-slot-id]");

  if (removeButton) {
    event.stopPropagation();
    const slotId = removeButton.dataset.removeSlotId;
    const result = await api(`/api/availability/${slotId}`, { method: "DELETE" });

    if (selectedSlotId === slotId) {
      selectedSlotId = result.state.selectedSlotId;
      if (selectedSlotId) {
        window.localStorage.setItem("oh_selected_slot_id", selectedSlotId);
      } else {
        window.localStorage.removeItem("oh_selected_slot_id");
      }
    }

    renderAll(result.state);
    return;
  }

  const slotButton = event.target.closest("[data-slot-id]");

  if (!slotButton) {
    return;
  }

  selectedSlotId = slotButton.dataset.slotId;
  window.localStorage.setItem("oh_selected_slot_id", selectedSlotId);
  await loadState();
});

availabilityForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const result = await api("/api/availability", {
    method: "POST",
    body: JSON.stringify({
      date: document.querySelector("#availabilityDate").value,
      startTime: document.querySelector("#availabilityStart").value,
      endTime: document.querySelector("#availabilityEnd").value,
      location: document.querySelector("#availabilityLocation").value,
      taName: "Bobby",
    }),
  });

  renderAll(result.state);
});

function buildStateQuery() {
  const params = new URLSearchParams();

  if (page === "student" && studentId) {
    params.set("studentId", studentId);
  }

  if (selectedSlotId) {
    params.set("slotId", selectedSlotId);
  }

  return params.toString() ? `?${params}` : "";
}

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
      notificationBody.textContent = "Start it with npm start, then refresh this page.";
    }
  });
}
