"""HTTP ownership checks shared by workspace and task endpoints."""

from fastapi import HTTPException

from app.persistence import storage


def owned(wid, user):
    workspace = storage.get(wid, user["id"])
    if not workspace:
        raise HTTPException(404, "未找到这次旅行")
    return workspace
