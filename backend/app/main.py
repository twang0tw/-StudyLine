from pathlib import Path
from typing import Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pymongo.errors import PyMongoError

from app.api import routes_auth, routes_courses, routes_queue, routes_slots, routes_state, routes_ta
from app.services import db_service


app = FastAPI(title="StudyLine API")

app.include_router(routes_auth.router)
app.include_router(routes_courses.router)
app.include_router(routes_slots.router)
app.include_router(routes_queue.router)
app.include_router(routes_state.router)
app.include_router(routes_ta.router)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALLOWED_FRONTEND_FILES = {"index.html", "student.html", "ta.html", "settings.html", "settings.js", "navigation.js", "app.js", "styles.css"}
NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, max-age=0, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}


@app.on_event("startup")
def startup() -> None:
    try:
        db_service.initialize_database()
    except PyMongoError as error:
        print(f"MongoDB startup check failed: {error}")


@app.exception_handler(PyMongoError)
def mongo_exception_handler(request, error):
    return JSONResponse(
        status_code=503,
        content={"detail": "Database is unavailable. Check MongoDB Atlas credentials, network access, and MONGO_URL."},
    )


@app.get("/health")
def health_check() -> Dict[str, str]:
    try:
        db_service.ping_database()
        database = "ok"
    except PyMongoError:
        database = "unavailable"
    return {"status": "ok", "database": database}


@app.get("/")
def home_page():
    return FileResponse(PROJECT_ROOT / "index.html", headers=NO_CACHE_HEADERS)


@app.get("/assets/{file_name}")
def brand_asset(file_name: str):
    if file_name not in {"studyline_tab_icon.png", "studyline_large_logo.png"}:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(PROJECT_ROOT / "assets" / file_name, headers=NO_CACHE_HEADERS)


@app.get("/{file_name}")
def frontend_file(file_name: str):
    if file_name not in ALLOWED_FRONTEND_FILES:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(PROJECT_ROOT / file_name, headers=NO_CACHE_HEADERS)
