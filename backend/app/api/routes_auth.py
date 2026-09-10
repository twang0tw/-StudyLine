import os

from fastapi import APIRouter, Header, HTTPException
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from pydantic import BaseModel, Field

from app.services import db_service


router = APIRouter(tags=["auth"])
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com")


class LoginRequest(BaseModel):
    credential: str
    role: str


class ProfileUpdateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    preferences: dict[str, bool] = Field(default_factory=dict)


@router.get("/api/auth/config")
def auth_config():
    return {
        "googleClientId": GOOGLE_CLIENT_ID,
        "googleConfigured": GOOGLE_CLIENT_ID != "YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com",
    }


@router.post("/api/auth/login")
def login(payload: LoginRequest):
    if payload.role not in {"student", "ta"}:
        raise HTTPException(status_code=400, detail="role must be student or ta")
    if GOOGLE_CLIENT_ID == "YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com":
        raise HTTPException(status_code=500, detail="Set GOOGLE_CLIENT_ID in .env before using Google login.")

    try:
        google_user = id_token.verify_oauth2_token(
            payload.credential,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
    except ValueError as error:
        raise HTTPException(status_code=401, detail="Google login token could not be verified.") from error

    if not google_user.get("email_verified"):
        raise HTTPException(status_code=401, detail="Google email is not verified.")

    email = google_user.get("email")
    name = google_user.get("name") or email.split("@")[0]
    google_sub = google_user.get("sub")

    try:
        result = db_service.login_user(email, name, payload.role, google_sub=google_sub)
        return db_service.serialize(result)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/api/auth/me")
def me(x_user_token: str | None = Header(default=None, alias="X-User-Token")):
    user = db_service.user_for_token(x_user_token)
    if not user:
        raise HTTPException(status_code=401, detail="Please sign in.")
    return {"user": db_service.serialize(user)}


@router.delete("/api/auth/session")
def logout(x_user_token: str | None = Header(default=None, alias="X-User-Token")):
    return {"signedOut": db_service.logout_user(x_user_token)}


@router.patch("/api/auth/profile")
def update_profile(
    payload: ProfileUpdateRequest,
    x_user_token: str | None = Header(default=None, alias="X-User-Token"),
):
    user = db_service.user_for_token(x_user_token)
    if not user:
        raise HTTPException(status_code=401, detail="Please sign in.")
    try:
        updated = db_service.update_user_profile(user["id"], payload.name, payload.preferences)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"user": db_service.serialize(updated)}
