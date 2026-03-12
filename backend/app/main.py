from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

if __package__ in {None, ""}:
    # Support `python main.py` from backend/app by exposing the backend root.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.routes.health import router as health_router
from app.api.routes.planning import router as planning_router
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="AI travel planner with MCP-based AMap integration.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(planning_router, prefix="/api/v1")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
