const http = require("http");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

loadEnvFile();

const PORT = Number(process.env.PORT || 5174);
const PUBLIC_DIR = __dirname;

const today = new Date().toISOString().slice(0, 10);

const forecast = [
  { time: "10 AM", level: 32, crowd: "low" },
  { time: "12 PM", level: 74, crowd: "high" },
  { time: "2 PM", level: 58, crowd: "medium" },
  { time: "4 PM", level: 24, crowd: "low" },
];

const state = {
  availability: [
    createSlot({ date: today, startTime: "11:30", taName: "Bobby", location: "Library 204" }),
    createSlot({ date: today, startTime: "13:00", taName: "Bobby", location: "STEM Center" }),
    createSlot({ date: today, startTime: "15:30", taName: "Bobby", location: "Library 204" }),
  ],
  queue: [
    {
      id: "demo-1",
      slotId: slotIdFor(today, "11:30"),
      name: "Maya",
      course: "CS 101",
      need: "Debugging help",
      message: "My loop stops after the first test case and I cannot tell whether it is an index issue.",
      file: { name: "lab4.py", type: "text/x-python", size: 4200 },
      ai: {
        summary: "Likely debugging support for a small programming issue involving loops or indexing.",
        estimatedHelpMinutes: 9,
        confidence: "medium",
        source: "demo",
      },
      status: "waiting",
      joinedAt: Date.now() - 20 * 60 * 1000,
    },
    {
      id: "demo-2",
      slotId: slotIdFor(today, "13:00"),
      name: "Jordan",
      course: "Calculus II",
      need: "Concept question",
      message: "I want to understand when to use integration by parts versus substitution.",
      file: null,
      ai: {
        summary: "Concept explanation request about choosing an integration technique.",
        estimatedHelpMinutes: 7,
        confidence: "medium",
        source: "demo",
      },
      status: "waiting",
      joinedAt: Date.now() - 13 * 60 * 1000,
    },
    {
      id: "demo-3",
      slotId: slotIdFor(today, "15:30"),
      name: "Sam",
      course: "Data Structures",
      need: "Assignment review",
      message: "Can someone review whether my binary search tree delete function handles all cases?",
      file: { name: "bst_delete.java", type: "text/x-java-source", size: 9800 },
      ai: {
        summary: "Code review request for a data structure deletion implementation with edge cases.",
        estimatedHelpMinutes: 14,
        confidence: "medium",
        source: "demo",
      },
      status: "waiting",
      joinedAt: Date.now() - 7 * 60 * 1000,
    },
  ],
  currentBySlot: {},
  servedBySlot: {},
  tasActive: 2,
  averageHelpMinutes: 7,
};

const mimeTypes = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
};

function slotIdFor(date, startTime) {
  return `slot-${date}-${startTime.replace(":", "")}`;
}

function createSlot({ date, startTime, taName = "Bobby", location = "Office Hours Room" }) {
  const start = new Date(`${date}T${startTime}:00`);
  const end = new Date(start.getTime() + 30 * 60 * 1000);
  const endTime = end.toTimeString().slice(0, 5);

  return {
    id: slotIdFor(date, startTime),
    date,
    startTime,
    endTime,
    taName,
    location,
  };
}

function formatTime(time) {
  const [hourText, minute] = time.split(":");
  const hour = Number(hourText);
  const suffix = hour >= 12 ? "PM" : "AM";
  const displayHour = hour % 12 || 12;
  return `${displayHour}:${minute} ${suffix}`;
}

function formatSlot(slot) {
  return `${formatTime(slot.startTime)} - ${formatTime(slot.endTime)}`;
}

function createThirtyMinuteSlots({ date, startTime, endTime, taName, location }) {
  const slots = [];
  let cursor = new Date(`${date}T${startTime}:00`);
  const end = new Date(`${date}T${endTime}:00`);

  while (cursor < end) {
    const slotStart = cursor.toTimeString().slice(0, 5);
    slots.push(createSlot({ date, startTime: slotStart, taName, location }));
    cursor = new Date(cursor.getTime() + 30 * 60 * 1000);
  }

  return slots;
}

function loadEnvFile() {
  const envPath = path.join(__dirname, ".env");

  if (!fs.existsSync(envPath)) {
    return;
  }

  const lines = fs.readFileSync(envPath, "utf8").split(/\r?\n/);

  for (const line of lines) {
    const trimmed = line.trim();

    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) {
      continue;
    }

    const [key, ...valueParts] = trimmed.split("=");
    const value = valueParts.join("=").trim().replace(/^["']|["']$/g, "");

    if (!process.env[key]) {
      process.env[key] = value;
    }
  }
}

function getEntryHelpMinutes(entry) {
  return entry?.ai?.estimatedHelpMinutes || state.averageHelpMinutes;
}

function estimateWait(entries = state.queue) {
  const totalHelpMinutes = entries.reduce((total, entry) => total + getEntryHelpMinutes(entry), 0);
  return Math.max(3, Math.round(totalHelpMinutes / state.tasActive));
}

function crowdForWait(wait) {
  if (wait <= 10) return "low";
  if (wait <= 22) return "medium";
  return "high";
}

function getSelectedSlotId(studentId, requestedSlotId) {
  const studentEntry = studentId
    ? state.queue.find((entry) => entry.id === studentId) || Object.values(state.currentBySlot).find((entry) => entry?.id === studentId)
    : null;

  return requestedSlotId || studentEntry?.slotId || state.availability[0]?.id || null;
}

function buildState(studentId, requestedSlotId) {
  const selectedSlotId = getSelectedSlotId(studentId, requestedSlotId);
  const waiting = state.queue.filter((entry) => entry.status === "waiting" && entry.slotId === selectedSlotId);
  const wait = estimateWait(waiting);
  const position = studentId ? waiting.findIndex((entry) => entry.id === studentId) + 1 : 0;
  const currentStudent = selectedSlotId ? state.currentBySlot[selectedSlotId] || null : null;
  const isCurrentStudent = Boolean(studentId && currentStudent && currentStudent.id === studentId);
  const personalEntries = position > 0 ? waiting.slice(0, position) : [];

  return {
    slots: state.availability.map((slot) => {
      const slotWaiting = state.queue.filter((entry) => entry.status === "waiting" && entry.slotId === slot.id);
      const slotWait = estimateWait(slotWaiting);

      return {
        ...slot,
        label: formatSlot(slot),
        studentsWaiting: slotWaiting.length,
        estimatedWaitMinutes: slotWait,
        crowd: crowdForWait(slotWait),
      };
    }),
    selectedSlotId,
    live: {
      studentsWaiting: waiting.length,
      tasActive: state.tasActive,
      averageHelpMinutes: state.averageHelpMinutes,
      estimatedWaitMinutes: wait,
      crowd: crowdForWait(wait),
    },
    queue: {
      studentId: studentId || null,
      position: position > 0 ? position : null,
      personalWaitMinutes: position > 0 ? estimateWait(personalEntries) : null,
      status: isCurrentStudent ? "called" : position === 1 ? "next" : position > 1 ? "waiting" : "not_joined",
    },
    staff: {
      currentStudent,
      waitingEntries: waiting.map((entry, index) => ({
        ...entry,
        position: index + 1,
        estimatedWaitMinutes: estimateWait(waiting.slice(0, index + 1)),
      })),
      servedCount: selectedSlotId ? state.servedBySlot[selectedSlotId] || 0 : 0,
    },
    sessions: state.availability.map((slot) => ({
      id: slot.id,
      time: formatSlot(slot),
      room: slot.location,
      wait: estimateWait(state.queue.filter((entry) => entry.status === "waiting" && entry.slotId === slot.id)),
      crowd: crowdForWait(estimateWait(state.queue.filter((entry) => entry.status === "waiting" && entry.slotId === slot.id))),
      note: `${slot.taName} available`,
    })),
    forecast,
  };
}

async function analyzeQuestion({ course, need, message, file }) {
  const apiKey = process.env.GEMINI_API_KEY;

  if (apiKey && apiKey !== "paste-your-gemini-api-key-here") {
    try {
      return await analyzeQuestionWithGemini({ course, need, message, file, apiKey });
    } catch (error) {
      console.warn(`Gemini analysis failed; using local fallback: ${error.message}`);
    }
  }

  return analyzeQuestionHeuristically({ course, need, message, file });
}

async function analyzeQuestionWithGemini({ course, need, message, file, apiKey }) {
  const model = process.env.GEMINI_MODEL || "gemini-2.5-flash";
  const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent`;
  const prompt = [
    "You are helping run an equitable college office-hours queue.",
    "Analyze this student request for a TA dashboard.",
    "Return only valid JSON with these exact fields:",
    "{",
    '  "summary": "one short sentence for the TA",',
    '  "estimatedHelpMinutes": number from 3 to 25,',
    '  "confidence": "low" | "medium" | "high"',
    "}",
    "",
    `Course: ${course || "General"}`,
    `Need category: ${need || "Office hours help"}`,
    `Student message: ${message || "No message provided"}`,
    file ? `Attached file: ${file.name} (${file.type || "unknown"}, ${file.size || 0} bytes)` : "Attached file: none",
    "",
    "Estimate more time for debugging, file/code review, vague questions, long messages, or requests involving multiple concepts.",
  ].join("\n");

  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-goog-api-key": apiKey,
    },
    body: JSON.stringify({
      contents: [
        {
          role: "user",
          parts: [{ text: prompt }],
        },
      ],
      generationConfig: {
        responseMimeType: "application/json",
        temperature: 0.2,
      },
    }),
  });

  const result = await response.json().catch(() => ({}));

  if (!response.ok) {
    const messageText = result?.error?.message || `HTTP ${response.status}`;
    throw new Error(messageText);
  }

  const text = result?.candidates?.[0]?.content?.parts?.map((part) => part.text || "").join("").trim();

  if (!text) {
    throw new Error("Gemini returned no text");
  }

  const parsed = parseJsonObject(text);
  const estimatedHelpMinutes = Math.max(3, Math.min(25, Math.round(Number(parsed.estimatedHelpMinutes) || 8)));
  const confidence = ["low", "medium", "high"].includes(parsed.confidence) ? parsed.confidence : "medium";

  return {
    summary: String(parsed.summary || "Student needs office hours support.").trim().slice(0, 240),
    estimatedHelpMinutes,
    confidence,
    source: "gemini",
    model,
  };
}

function parseJsonObject(text) {
  try {
    return JSON.parse(text);
  } catch {
    const match = text.match(/\{[\s\S]*\}/);

    if (!match) {
      throw new Error("Gemini returned non-JSON output");
    }

    return JSON.parse(match[0]);
  }
}

function analyzeQuestionHeuristically({ course, need, message, file, source = "local-heuristic" }) {
  const text = `${course} ${need} ${message || ""}`.toLowerCase();
  let minutes = 6;
  const reasons = [];

  if (text.includes("debug") || text.includes("error") || text.includes("bug")) {
    minutes += 4;
    reasons.push("debugging");
  }

  if (text.includes("review") || text.includes("check") || text.includes("edge case")) {
    minutes += 3;
    reasons.push("review");
  }

  if (text.includes("exam") || text.includes("proof") || text.includes("concept")) {
    minutes += 2;
    reasons.push("concept explanation");
  }

  if ((message || "").length > 180) {
    minutes += 2;
    reasons.push("detailed question");
  }

  if (file) {
    minutes += file.size > 8000 ? 4 : 2;
    reasons.push("attached file");
  }

  return {
    summary: buildQuestionSummary({ course, need, message, file, reasons }),
    estimatedHelpMinutes: Math.min(22, minutes),
    confidence: message || file ? "medium" : "low",
    source,
  };
}

function buildQuestionSummary({ course, need, message, file, reasons }) {
  const base = message
    ? message.trim().replace(/\s+/g, " ").slice(0, 150)
    : `${need} for ${course}`;
  const fileText = file ? ` File attached: ${file.name}.` : "";
  const reasonText = reasons.length ? ` Signals: ${reasons.join(", ")}.` : "";
  return `${base}${fileText}${reasonText}`;
}

function sendJson(res, status, body) {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(payload),
  });
  res.end(payload);
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let body = "";
    req.on("data", (chunk) => {
      body += chunk;
      if (body.length > 1_000_000) {
        req.destroy();
        reject(new Error("Request body too large"));
      }
    });
    req.on("end", () => {
      if (!body) {
        resolve({});
        return;
      }

      try {
        resolve(JSON.parse(body));
      } catch (error) {
        reject(error);
      }
    });
    req.on("error", reject);
  });
}

function serveStatic(req, res) {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const requestedPath = url.pathname === "/" ? "/index.html" : url.pathname;
  const filePath = path.normalize(path.join(PUBLIC_DIR, requestedPath));

  if (!filePath.startsWith(PUBLIC_DIR) || filePath === __filename) {
    res.writeHead(404);
    res.end("Not found");
    return;
  }

  fs.readFile(filePath, (error, data) => {
    if (error) {
      res.writeHead(404);
      res.end("Not found");
      return;
    }

    res.writeHead(200, {
      "Content-Type": mimeTypes[path.extname(filePath)] || "application/octet-stream",
    });
    res.end(data);
  });
}

async function handleApi(req, res) {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const parts = url.pathname.split("/").filter(Boolean);

  if (req.method === "GET" && url.pathname === "/api/state") {
    sendJson(res, 200, buildState(url.searchParams.get("studentId"), url.searchParams.get("slotId")));
    return;
  }

  if (req.method === "POST" && url.pathname === "/api/availability") {
    const body = await readJson(req);
    const date = String(body.date || today).slice(0, 10);
    const startTime = String(body.startTime || "09:00").slice(0, 5);
    const endTime = String(body.endTime || startTime).slice(0, 5);
    const taName = String(body.taName || "Bobby").trim().slice(0, 80);
    const location = String(body.location || "Office Hours Room").trim().slice(0, 100);
    const slots = createThirtyMinuteSlots({ date, startTime, endTime, taName, location });

    for (const slot of slots) {
      if (!state.availability.some((existing) => existing.id === slot.id)) {
        state.availability.push(slot);
      }
    }

    state.availability.sort((a, b) => `${a.date}T${a.startTime}`.localeCompare(`${b.date}T${b.startTime}`));
    sendJson(res, 201, { slots, state: buildState(null, slots[0]?.id) });
    return;
  }

  if (req.method === "DELETE" && parts[0] === "api" && parts[1] === "availability" && parts[2]) {
    const slotId = parts[2];
    const before = state.availability.length;
    state.availability = state.availability.filter((slot) => slot.id !== slotId);
    state.queue = state.queue.filter((entry) => entry.slotId !== slotId);
    delete state.currentBySlot[slotId];
    delete state.servedBySlot[slotId];

    sendJson(res, 200, {
      removed: before !== state.availability.length,
      state: buildState(null, state.availability[0]?.id),
    });
    return;
  }

  if (req.method === "POST" && url.pathname === "/api/queue") {
    const body = await readJson(req);
    const slotId = String(body.slotId || "").trim();
    const selectedSlot = state.availability.find((slot) => slot.id === slotId);

    if (!selectedSlot) {
      sendJson(res, 400, { error: "Choose an available office-hour time slot before joining." });
      return;
    }

    const file = body.file
      ? {
          name: String(body.file.name || "Attached file").trim().slice(0, 120),
          type: String(body.file.type || "unknown").trim().slice(0, 80),
          size: Number(body.file.size || 0),
        }
      : null;
    const message = String(body.message || "").trim().slice(0, 1200);
    const ai = await analyzeQuestion({
      course: body.course,
      need: body.need,
      message,
      file,
    });
    const entry = {
      id: crypto.randomUUID(),
      slotId,
      name: String(body.name || "Student").trim().slice(0, 80),
      course: String(body.course || "General").trim().slice(0, 80),
      need: String(body.need || "Office hours help").trim().slice(0, 120),
      message,
      file,
      ai,
      status: "waiting",
      joinedAt: Date.now(),
    };

    state.queue.push(entry);
    sendJson(res, 201, { entry, state: buildState(entry.id, slotId) });
    return;
  }

  if (req.method === "DELETE" && parts[0] === "api" && parts[1] === "queue" && parts[2]) {
    const before = state.queue.length;
    state.queue = state.queue.filter((entry) => entry.id !== parts[2]);
    sendJson(res, 200, { removed: before !== state.queue.length, state: buildState(null, url.searchParams.get("slotId")) });
    return;
  }

  if (req.method === "POST" && url.pathname === "/api/staff/call-next") {
    const slotId = getSelectedSlotId(url.searchParams.get("studentId"), url.searchParams.get("slotId"));

    if (state.currentBySlot[slotId]) {
      state.servedBySlot[slotId] = (state.servedBySlot[slotId] || 0) + 1;
    }

    const nextIndex = state.queue.findIndex((entry) => entry.status === "waiting" && entry.slotId === slotId);
    const next = nextIndex >= 0 ? state.queue.splice(nextIndex, 1)[0] : null;

    if (next) {
      next.status = "called";
      next.calledAt = Date.now();
    }

    state.currentBySlot[slotId] = next;
    sendJson(res, 200, { next, state: buildState(url.searchParams.get("studentId"), slotId) });
    return;
  }

  if (req.method === "POST" && url.pathname === "/api/staff/serve-current") {
    const slotId = getSelectedSlotId(url.searchParams.get("studentId"), url.searchParams.get("slotId"));
    const served = state.currentBySlot[slotId];

    if (served) {
      state.servedBySlot[slotId] = (state.servedBySlot[slotId] || 0) + 1;
      state.currentBySlot[slotId] = null;
    }

    sendJson(res, 200, { served, state: buildState(url.searchParams.get("studentId"), slotId) });
    return;
  }

  if (req.method === "POST" && url.pathname === "/api/simulate-crowd") {
    const slotId = getSelectedSlotId(url.searchParams.get("studentId"), url.searchParams.get("slotId"));
    state.tasActive = Math.random() > 0.78 ? 3 : 2;
    state.averageHelpMinutes = 6 + Math.floor(Math.random() * 4);

    if (Math.random() > 0.5) {
      state.queue.push({
        id: crypto.randomUUID(),
        slotId,
        name: "Walk-in Student",
        course: "General",
        need: "Quick question",
        message: "Short walk-in question.",
        file: null,
        ai: {
          summary: "Short walk-in question.",
          estimatedHelpMinutes: 5,
          confidence: "low",
          source: "simulation",
        },
        status: "waiting",
        joinedAt: Date.now(),
      });
    } else if (state.queue.length > 1) {
      const removeIndex = state.queue.findIndex((entry) => entry.slotId === slotId);

      if (removeIndex >= 0) {
        state.queue.splice(removeIndex, 1);
      }
    }

    sendJson(res, 200, buildState(url.searchParams.get("studentId"), slotId));
    return;
  }

  sendJson(res, 404, { error: "API route not found" });
}

const server = http.createServer((req, res) => {
  if (req.url.startsWith("/api/")) {
    handleApi(req, res).catch((error) => {
      sendJson(res, 400, { error: error.message || "Bad request" });
    });
    return;
  }

  serveStatic(req, res);
});

server.listen(PORT, () => {
  console.log(`StudyLine running at http://localhost:${PORT}`);
});
