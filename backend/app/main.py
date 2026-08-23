from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import chat, health, me
from app.planner.routes import router as planner_router
from app.recommendations.router import router as recommendations_router

app = FastAPI(title="ForexCast API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(me.router)
app.include_router(chat.router)
app.include_router(planner_router)
app.include_router(recommendations_router)
