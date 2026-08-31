Here’s a concise map of the project and what that comment about buildState is asking for.

What “dedicated read-model / state service” means
In server.js, buildState does not change data. It reads the in-memory state object (availability, queue, who’s being helped, etc.) and assembles one JSON blob shaped exactly for the UI: slot list with wait/crowd, live stats, your place in line, staff queue, sessions, forecast.

// Keep: Builds the full frontend state payload for both student and staff views.
// Python rewrite note: This should become a dedicated read-model/state service.
function buildState(studentId, requestedSlotId) {
  const selectedSlotId = getSelectedSlotId(studentId, requestedSlotId);
  const waiting = state.queue.filter((entry) => entry.status === "waiting" && entry.slotId === selectedSlotId);
  // ... computes waits, positions, staff view ...
  return {
    slots: ...,
    selectedSlotId,
    live: { ... },
    queue: { ... },
    staff: { ... },
    sessions: ...,
    forecast,
  };
}
“Read-model” (from CQRS-style thinking) means: a view optimized for reading/display, built from underlying facts (queue rows, slots, “current student” per slot). It’s separate from commands that change things (join queue, call next, add availability).

“Dedicated state service” means: don’t leave this logic inside route handlers or mixed with writes. Put it in something like backend/app/services/state.py (or split helpers: queue_read_model.py, slot_overview.py) that:

Takes inputs (DB/repo data + student_id / slot_id / tokens)
Runs pure projection (estimate_wait, crowd_level, position, staff list)
Returns DTOs for API responses
Your friends started that split in Python already: scheduling.py has estimate_wait, crowd_level, etc., and build_state is stubbed at the bottom of that file.

Important nuance: The current app.js no longer calls one giant GET /api/state. It was refactored to many smaller GETs and builds page state on the client:

Old (Node server.js)	New (frontend expects)
GET /api/state?studentId=&slotId=
GET /api/slots, GET /api/slots/{id}/overview, GET /api/queue/me, …
So you’re not necessarily one Python function named build_state() returning everything. You are porting the same projection rules into a read-side service, then exposing them through those focused endpoints (or one internal service used by several routes).

Writes vs reads today in Node:

Writes: POST queue, POST availability, POST call-next, etc. → mutate state, then call buildState() and return { ..., state: buildState(...) }.
Reads: GET /api/state → only buildState().
In Python, keep that separation: command handlers update DB; read service builds responses.

What StudyLine is
StudyLine is a demo/MVP for virtual office-hours queues: students pick a time slot, join a line remotely, see estimated wait; TAs manage who’s next and mark visits done. Optional Gemini (or heuristics) estimates how long each question might take, which feeds wait math.

Original backend (server.js)
Single Node process on port 5174 (default):

Serves static files — index.html, student.html, ta.html, styles.css, app.js.
Holds all data in memory — state with availability, queue, currentBySlot, servedBySlot, plus demo seed data.
REST API under /api/:
Endpoint	Role
GET /api/state
Full dashboard snapshot (buildState)
POST /api/availability
TA adds 30‑min blocks from a time range
DELETE /api/availability/:id
Remove slot + related queue state
POST /api/queue
Student joins (runs AI triage)
DELETE /api/queue/:id
Leave queue
POST /api/staff/call-next
Call next student for a slot
POST /api/staff/serve-current
Mark current done
POST /api/simulate-crowd
Demo: random queue churn
No database, no auth (student identity was a UUID in query/localStorage; the new frontend uses tokens instead).

Core domain helpers in the same file: slot IDs, 30‑min slot expansion, wait estimation, buildState, AI analysis.

Frontend (vanilla HTML + app.js)
Three pages, one shared script:

index.html — pick Student vs TA.
student.html (data-page="student") — join line, crowd, recommendations, forecast, “your turn” UI.
ta.html (data-page="ta") — add/remove availability, call next, mark served, queue list with AI summaries.
app.js flow:

On load, loadState() parallel-fetches several APIs and merges into appState.
Renders DOM sections (renderLiveData, renderStaffDashboard, etc.).
Mutations (join, leave, call next) POST/DELETE, then refreshAfterMutation() refetches.
It expects a FastAPI backend (see comment at top of app.js); if the server isn’t up, it shows “Backend is not running.”

Identity: localStorage holds queue_token, session_token, selected_slot_id (not raw student IDs). Requests send X-Queue-Token / X-Session-Token.

Staff optimization: Light list from GET /api/staff/queue, then per-entry GET /api/staff/queue/{entryId} for full message/AI (avoids huge polls).

Python backend (in progress)
backend/app/main.py — FastAPI app; so far mostly /health and a debug slot-id route.
backend/app/services/scheduling.py — ports slot_id_for, create_slot, create_thirty_minute_slots, estimate_wait, crowd_level; build_state / get_selected_slot_id are incomplete.
Run Node for the old all-in-one stack: npm start. Run FastAPI separately for the migration (typical: uvicorn on another port); the frontend is already written for the new API shape.

Mental model (one diagram)
Browser
Node server.js
Python target
today: designed for
legacy: still in repo
student.html / ta.html
app.js
/api/* routes/
in-memory state
buildState read-model
FastAPI routes
state / scheduling services
DB later
Practical takeaway for your rewrite
buildState logic = read-model service — aggregate + compute for display; no side effects.
Expose it either as one internal module used by many routes (matching app.js) or, if you keep Node parity temporarily, one GET /api/state that delegates to that service.
Don’t put wait/position/crowd math inside POST handlers; call the read service after writes (or have the client refetch read endpoints, as app.js already does).
scheduling.py is the right home for slot/wait math; a sibling module (e.g. state.py) fits slot overview, queue status, and staff queue projections.
If you want, next step can be a file-by-file checklist mapping each server.js function to a Python module and which FastAPI route should call it.



DB:
Yes, this is the right next thing to learn. The mental shift is:

`server.js state` is one big in-memory object.

MongoDB `app_state` should become a set of collection reads/writes that recreate the same shape only when your services need it.

Don’t start by writing Mongo code. Start by finding each `state` access in `server.js` and labeling what it means.

Run this:

```bash
rg -n "state\\." server.js
```

You’ll see patterns like:

```js
state.availability
state.queue
state.currentBySlot
state.servedBySlot
state.tasActive
state.averageHelpMinutes
state.forecast
```

Treat each top-level field as either a Mongo collection or a settings document.

I’d map them like this:

```text
state.availability      -> slots collection
state.queue             -> queue_entries collection
state.currentBySlot     -> current_students collection
state.servedBySlot      -> served_counts collection
state.tasActive         -> app_settings document
state.averageHelpMinutes -> app_settings document
state.forecast          -> forecasts collection or demo/settings document
studentSessions         -> student_sessions collection
```

So your current [db_service.py](/Users/MaxCai/PycharmProjects/-StudyLine/backend/app/services/db_service.py:14) should eventually stop exporting this:

```python
app_state = {
    "availability": [...],
    "queue": [...],
    "currentBySlot": {},
    ...
}
```

and start exporting functions like:

```python
def list_slots():
    ...

def list_queue_entries():
    ...

def insert_queue_entry(entry):
    ...

def get_current_by_slot():
    ...

def increment_served_count(slot_id):
    ...
```

The important idea: **routes should not know whether storage is memory or MongoDB**.

Right now your routes do this:

```python
app_state["queue"].append(entry)
```

That is local-memory style.

MongoDB style should become:

```python
db_service.insert_queue_entry(entry)
```

Then inside `db_service.py`, you do the Mongo operation.

Example using your JS as reference:

In `server.js`, queue join is here:

```js
state.queue.push(entry);
```

That tells you the Python Mongo replacement should be an insert:

```python
def insert_queue_entry(entry):
    queue_entries.insert_one(entry)
```

Then the route changes from:

```python
app_state["queue"].append(entry)
```

to:

```python
db_service.insert_queue_entry(entry)
```

Another example:

In `server.js`, delete queue entry is:

```js
state.queue = state.queue.filter((entry) => entry.id !== parts[2]);
```

That means Mongo replacement is delete-by-id:

```python
def delete_queue_entry(entry_id):
    result = queue_entries.delete_one({"id": entry_id})
    return result.deleted_count > 0
```

Another:

```js
state.availability = state.availability.filter((slot) => slot.id !== slotId);
state.queue = state.queue.filter((entry) => entry.slotId !== slotId);
delete state.currentBySlot[slotId];
delete state.servedBySlot[slotId];
```

Mongo version is multiple operations:

```python
def delete_slot(slot_id):
    slots.delete_one({"id": slot_id})
    queue_entries.delete_many({"slotId": slot_id})
    current_students.delete_one({"slotId": slot_id})
    served_counts.delete_one({"slotId": slot_id})
```

So your migration process should be:

1. Find the JS state operation.
2. Ask: is it reading, inserting, updating, deleting, or aggregating?
3. Write a `db_service.py` function with a plain name.
4. Replace direct `app_state[...]` use in the route with that function.
5. Keep `state_service.build_state()` mostly unchanged by feeding it lists/dicts returned from Mongo.

For `build_state()`, you don’t want it querying Mongo directly. Keep it as a pure read-model builder.

Instead of:

```python
state_service.build_state(
    slots=app_state["availability"],
    queue_entries=app_state["queue"],
    current_by_slot=app_state["currentBySlot"],
    served_by_slot=app_state["servedBySlot"],
)
```

you eventually want:

```python
state_service.build_state(
    slots=db_service.list_slots(),
    queue_entries=db_service.list_queue_entries(),
    current_by_slot=db_service.get_current_by_slot(),
    served_by_slot=db_service.get_served_by_slot(),
    tas_active=db_service.get_setting("tasActive", 2),
    avg_help_minutes=db_service.get_setting("averageHelpMinutes", 7),
    forecast=db_service.list_forecast(),
)
```

That lets `state_service.py` stay clean. It receives ordinary Python data and doesn’t care where it came from.

A small first exercise I’d do next: migrate only `state.availability`.

Start with these three functions in `db_service.py`:

```python
def list_slots():
    return list(slots_collection.find({}, {"_id": 0}))

def insert_slots(new_slots):
    existing_ids = {slot["id"] for slot in list_slots()}
    fresh_slots = [slot for slot in new_slots if slot["id"] not in existing_ids]
    if fresh_slots:
        slots_collection.insert_many(fresh_slots)
    return fresh_slots

def delete_slot(slot_id):
    result = slots_collection.delete_one({"id": slot_id})
    queue_entries_collection.delete_many({"slotId": slot_id})
    current_students_collection.delete_one({"slotId": slot_id})
    served_counts_collection.delete_one({"slotId": slot_id})
    return result.deleted_count > 0
```

Then change only [routes_slots.py](/Users/MaxCai/PycharmProjects/-StudyLine/backend/app/api/routes_slots.py:47) to use those functions. Once slots work, do queue entries next.

Tiny rule of thumb: if the JS line uses `.push()`, Mongo probably uses `insert_one()` or `insert_many()`. If the JS line uses `.filter()`, Mongo probably uses `delete_one()`, `delete_many()`, or `find()`. If the JS line assigns a property like `state.currentBySlot[slotId] = next`, Mongo probably uses `update_one(..., upsert=True)`.