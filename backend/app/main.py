"""FastAPI 应用入口。

本地运行：

```powershell
cd backend
python -m uvicorn app.main:app --reload
```
"""

from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import router
from app.core import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI旅行决策与动态行程助手 API",
        version="0.1.0",
        description="C 线后端接口。当前实现会话与追问/推荐回路，攻略接口属于 C7。",
    )
    app.include_router(router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "plan_store_backend": settings.plan_store_backend,
        }

    return app


app = create_app()
