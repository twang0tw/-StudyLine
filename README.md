# StudyLine

Python/FastAPI office-hours queue MVP with MongoDB-backed courses, sections, sharing, and live queues.

## Run

Create `.env` in the project root:

```env
MONGO_URL="mongodb+srv://<username>:<password>@<cluster-url>/?retryWrites=true&w=majority&appName=studyline"
MONGO_DB_NAME="studyline"
DB_RETENTION_DAYS=30
GOOGLE_CLIENT_ID="YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com"
# Optional: enables model-backed queue summaries and estimates.
OPENAI_API_KEY="YOUR_OPENAI_API_KEY"
OPENAI_MODEL="gpt-5-mini"
```

Install dependencies:

```powershell
python -m pip install -r backend\requirements.txt
```

Start the Python backend and frontend:

```powershell
npm run dev
```

Open:

```text
http://127.0.0.1:8010/
```

## Google OAuth

The student and TA login pages use Google Identity Services. The browser receives a Google ID token, and the FastAPI backend verifies that token before creating a StudyLine session.

Create a Google OAuth 2.0 **Web application** client and replace the placeholder `GOOGLE_CLIENT_ID`. For local development, add this authorized JavaScript origin:

```text
http://127.0.0.1:8010
```

## Main Pages

- `student.html`: student login, course dashboard, shared-code join, live section queue.
- `ta.html`: TA login, course dashboard, weekly section schedule, past participated sections, sharing, editing, live queue.
