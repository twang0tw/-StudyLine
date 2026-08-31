# StudyLine

AI-assisted office-hours queue MVP.

## Run The Python Backend

Create a `.env` file in the project root:

```env
MONGO_URL="mongodb+srv://<username>:<password>@<cluster-url>/?retryWrites=true&w=majority&appName=studyline"
MONGO_DB_NAME="studyline"
DB_RETENTION_DAYS=30
```

Install dependencies:

```powershell
python -m pip install -r backend\requirements.txt
```

Start the FastAPI app:

```powershell
npm run dev
```

Then open:

```text
http://127.0.0.1:8010
```

The old Node backend is still available for comparison:

```powershell
npm run start:node
```
