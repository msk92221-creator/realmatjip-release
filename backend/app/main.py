"""FastAPI 앱 팩토리. 실행: uvicorn app.main:app --host 0.0.0.0 --port 8000"""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from . import SCORING_ALGORITHM_VERSION
from .api import API_ROUTES
from .core.security import require_auth
from .core.settings import Settings, get_settings
from .db.database import init_db, make_engine, make_session_factory
from .config import ScoringConfig


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(app.state.engine)
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = make_engine(settings.database_url())

    app = FastAPI(title="realmatjip-backend", version=SCORING_ALGORITHM_VERSION, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.scoring_config = ScoringConfig()

    for router in API_ROUTES:
        app.include_router(router, dependencies=[Depends(require_auth)])

    @app.get("/health", tags=["system"])
    def health():
        return {"status": "ok", "version": SCORING_ALGORITHM_VERSION}

    return app


app = create_app()
