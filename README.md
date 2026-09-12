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

## Deploy on Render

The repository includes a `render.yaml` Blueprint for an always-on live demo using Render's
smallest paid web-service instance. In Render, create a **Blueprint**, connect this GitHub
repository, and enter the requested secret values:

- `MONGO_URL`: your MongoDB Atlas connection string.
- `GOOGLE_CLIENT_ID`: the same Google OAuth web client ID used locally.
- `OPENAI_API_KEY`: the server-side OpenAI API key used for AI summaries and estimates.

After Render assigns the service URL, add its origin (for example,
`https://studyline.onrender.com`) to the Google OAuth client's **Authorized JavaScript origins**.
MongoDB Atlas must also allow connections from Render. Keep credentials in Render's environment
settings; never commit `.env`.

Every commit to the linked branch deploys automatically. Render checks `/health` and only sends
traffic to a version that can connect to MongoDB.

## Main Pages

- `frontend/student.html`: student login, course dashboard, shared-code join, live section queue.
- `frontend/ta.html`: TA login, course dashboard, weekly section schedule, past participated sections, sharing, editing, live queue.
