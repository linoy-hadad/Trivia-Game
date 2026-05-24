from __future__ import annotations

from pathlib import Path
from typing import Any

import socketio
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from game_engine import GameEngine
from question_store import QuestionStore


BASE_DIR = Path(__file__).parent

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
fastapi_app = FastAPI(title="Socket.IO Trivia Game")


async def emit(event: str, data: dict[str, Any], target: str | None = None) -> None:
    await sio.emit(event, data, room=target)


async def join_room(sid: str, room: str) -> None:
    await sio.enter_room(sid, room)


async def leave_room(sid: str, room: str) -> None:
    await sio.leave_room(sid, room)


engine = GameEngine(QuestionStore(BASE_DIR / "trivia.db"), emit, join_room)


@fastapi_app.get("/")
async def index() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


fastapi_app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app = socketio.ASGIApp(sio, fastapi_app)


@sio.event
async def connect(sid: str, environ: dict[str, Any], auth: Any) -> None:
    await sio.emit("connected", {"sid": sid}, room=sid)


@sio.event
async def disconnect(sid: str) -> None:
    await engine.disconnect(sid)


@sio.event
async def join(sid: str, data: dict[str, Any]) -> None:
    await engine.join(sid, str(data.get("nickname", "")))


@sio.event
async def vote_category(sid: str, data: dict[str, Any]) -> None:
    await engine.vote_category(sid, str(data.get("category", "")))


@sio.event
async def vote_final_challenge(sid: str, data: dict[str, Any]) -> None:
    await engine.vote_final_challenge(sid, str(data.get("vote", "")))


@sio.event
async def submit_answer(sid: str, data: dict[str, Any]) -> None:
    await engine.submit_answer(sid, str(data.get("optionId", "")))


@sio.event
async def use_help(sid: str, data: dict[str, Any]) -> None:
    await engine.use_help(sid, str(data.get("helpType", "")))


@sio.event
async def chat_message(sid: str, data: dict[str, Any]) -> None:
    await engine.chat_message(sid, str(data.get("message", "")))


@sio.event
async def emoji(sid: str, data: dict[str, Any]) -> None:
    await engine.emoji(sid, str(data.get("emoji", "")))


@sio.event
async def finish_game(sid: str) -> None:
    room_id = await engine.leave_game(sid)
    if room_id:
        await leave_room(sid, room_id)
    await sio.emit("finished_game", {}, room=sid)
