import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.middleware import verify_api_key
from app.sockets.sio_app import socket_app
from app.routes.api.v1 import operator, cua

app = FastAPI(
    title="Automata API",
    description="This is API for Automata Web Operator",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(operator.router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])
app.include_router(cua.router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])

app.mount("/socket.io", socket_app)
