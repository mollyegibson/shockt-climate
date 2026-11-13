"""FastAPI application for the ShockT Climate route calculator."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shockt_api.db import load_cached_data
from shockt_api.disruptions import router as disruptions_router
from shockt_api.nodes import init_nodes
from shockt_api.nodes import router as nodes_router
from shockt_api.routes import init_routes
from shockt_api.routes import router as routes_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    database_url = os.environ["DATABASE_URL"]
    data = load_cached_data(database_url)
    init_routes(data)
    init_nodes(database_url)
    yield


app = FastAPI(title="ShockT Climate Route Calculator", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("ALLOWED_ORIGINS", "*").split(","),
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(routes_router)
app.include_router(nodes_router)
app.include_router(disruptions_router)
