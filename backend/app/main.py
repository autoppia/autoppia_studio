from fastapi import FastAPI

from app.middleware import verify_api_key
from app.sockets.sio_app import socket_app
from app.routes.api.v1 import operator, cua

app = FastAPI(
    title="Automata API",
    description="This is API for Automata Web Operator",
    version="1.0.0",
)

app.middleware("http")(verify_api_key)

app.mount("/ws", socket_app)
app.include_router(operator.router, prefix="/api/v1")
app.include_router(cua.router, prefix="/api/v1")
