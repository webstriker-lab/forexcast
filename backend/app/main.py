from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health

app = FastAPI(title="ForexCast API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tightened to a real origin in the deployment task
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
