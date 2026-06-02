from typing import Annotated

import firebase_admin
from fastapi import Depends, Header, HTTPException, status
from firebase_admin import auth, credentials

from app.config import Settings, get_settings


def initialize_firebase(settings: Settings) -> None:
    if not settings.firebase_project_id or firebase_admin._apps:
        return

    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"projectId": settings.firebase_project_id})


async def require_admin(
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> dict:
    if not settings.firebase_project_id:
        return {"uid": "local-dev", "admin": True}

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Firebase bearer token.",
        )

    token = authorization.removeprefix("Bearer ").strip()

    try:
        decoded = auth.verify_id_token(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase bearer token.",
        ) from exc

    if not decoded.get("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin claim required.",
        )

    return decoded
