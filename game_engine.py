from __future__ import annotations

import asyncio
import html
import random
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Any

from llm_help import get_friend_advice
from question_store import CATEGORY_MAP, Question, QuestionStore, question_timer, shuffled_options


MATCHMAKING_SECONDS = 30
CATEGORY_SECONDS = 15
QUESTIONS_PER_GAME = 10
BASE_POINTS = 1000
HELP_TYPES = {"fifty_fifty", "call_friend", "double_score"}
EMOJIS = {"😀", "😂", "🔥", "👏", "🤯", "😎", "💀", "🎉", "❤️", "👍"}

Emit = Callable[[str, dict[str, Any], str | None], Awaitable[None]]
RoomJoin = Callable[[str, str], Awaitable[None]]


@dataclass
class Player:
    id: str
    nickname: str
    is_bot: bool = False
    score: int = 0
    helps: dict[str, bool] = field(
        default_factory=lambda: {"fifty_fifty": True, "call_friend": True, "double_score": True}
    )
    double_active: bool = False


@dataclass
class AnswerRecord:
    option_id: str
    response_time: float
    correct: bool
    points: int


@dataclass
class CurrentQuestion:
    question: Question
    options: list[dict[str, str]]
    correct_option_id: str
    timer: int
    started_at: float
    answers: dict[str, AnswerRecord] = field(default_factory=dict)


@dataclass
class GameRoom:
    id: str
    players: dict[str, Player]
    category_votes: dict[str, str] = field(default_factory=dict)
    category: str = "Mixed"
    difficulty: int = 1
    question_number: int = 0
    used_question_ids: set[int] = field(default_factory=set)
    current: CurrentQuestion | None = None


class GameEngine:
    def __init__(self, store: QuestionStore, emit: Emit, join_room: RoomJoin) -> None:
        self.store = store
        self.emit = emit
        self.join_room = join_room
        self.waiting: dict[str, Player] = {}
        self.sid_to_room: dict[str, str] = {}
        self.rooms: dict[str, GameRoom] = {}
        self.lobby_task: asyncio.Task[None] | None = None
        self.lock = asyncio.Lock()

    async def join(self, sid: str, nickname: str) -> None:
        nickname = self._unique_nickname(_clean(nickname) or "Player")
        async with self.lock:
            self.waiting[sid] = Player(id=sid, nickname=nickname)
            if not self.lobby_task or self.lobby_task.done():
                self.lobby_task = asyncio.create_task(self._finish_matchmaking_after_delay())
        await self._emit_lobby_update()

    async def disconnect(self, sid: str) -> None:
        async with self.lock:
            self.waiting.pop(sid, None)
            room = self.rooms.get(self.sid_to_room.pop(sid, ""))
            if room:
                room.players.pop(sid, None)
        await self._emit_lobby_update()

    async def vote_category(self, sid: str, category: str) -> None:
        room = self._room_for_sid(sid)
        if not room or category not in CATEGORY_MAP or room.current:
            return
        room.category_votes[sid] = category
        await self.emit("category_vote_update", self._vote_payload(room), room.id)

    async def submit_answer(self, sid: str, option_id: str) -> None:
        room = self._room_for_sid(sid)
        if not room or not room.current or sid not in room.players:
            return
        record = self._record_answer(room, sid, option_id, time.monotonic())
        if record:
            await self.emit(
                "answer_result",
                {"correct": record.correct, "points": record.points, "score": room.players[sid].score},
                sid,
            )
            await self.emit("scoreboard_update", {"leaderboard": self._leaderboard(room)}, room.id)

    async def use_help(self, sid: str, help_type: str) -> None:
        room = self._room_for_sid(sid)
        if not room or not room.current or sid not in room.players or help_type not in HELP_TYPES:
            return
        player = room.players[sid]
        if player.is_bot or not player.helps.get(help_type):
            await self.emit("help_result", {"helpType": help_type, "error": "This help is not available."}, sid)
            return

        player.helps[help_type] = False
        if help_type == "double_score":
            player.double_active = True
            payload = {"helpType": help_type, "message": "Double score armed for this question."}
        elif help_type == "fifty_fifty":
            incorrect = [o["id"] for o in room.current.options if o["id"] != room.current.correct_option_id]
            payload = {"helpType": help_type, "removeOptionIds": random.sample(incorrect, 2)}
        else:
            advice = await get_friend_advice(room.current.question.text, room.current.options)
            payload = {"helpType": help_type, "message": advice}
        payload["helps"] = player.helps
        await self.emit("help_result", payload, sid)

    async def chat_message(self, sid: str, message: str) -> None:
        room = self._room_for_sid(sid)
        message = _clean(message, limit=180)
        if not message:
            return

        if room and sid in room.players and not room.players[sid].is_bot:
            await self.emit("chat_message", {"nickname": room.players[sid].nickname, "message": message}, room.id)
            return

        player = self.waiting.get(sid)
        if player and not player.is_bot:
            await self.emit("chat_message", {"nickname": player.nickname, "message": message}, None)

    async def emoji(self, sid: str, emoji: str) -> None:
        room = self._room_for_sid(sid)
        if not room or sid not in room.players or room.players[sid].is_bot:
            return
        if emoji in EMOJIS:
            await self.emit("emoji", {"nickname": room.players[sid].nickname, "emoji": emoji}, room.id)

    async def _finish_matchmaking_after_delay(self) -> None:
        await asyncio.sleep(MATCHMAKING_SECONDS)
        async with self.lock:
            players = self.waiting
            self.waiting = {}
        if not players:
            return

        humans = list(players.values())
        if len(humans) == 1:
            for bot in self._make_bots():
                players[bot.id] = bot

        room_id = f"room-{int(time.time() * 1000)}-{random.randint(100, 999)}"
        room = GameRoom(id=room_id, players=players)
        self.rooms[room_id] = room
        for player_id, player in players.items():
            self.sid_to_room[player_id] = room_id
            if not player.is_bot:
                await self.join_room(player_id, room_id)

        await self.emit("category_vote_started", self._vote_payload(room), room_id)
        await asyncio.sleep(CATEGORY_SECONDS)
        await self._start_game(room)

    async def _start_game(self, room: GameRoom) -> None:
        room.category = self._resolve_category(room)
        await self.emit(
            "game_started",
            {"category": room.category, "players": self._players_payload(room), "leaderboard": self._leaderboard(room)},
            room.id,
        )
        for _ in range(QUESTIONS_PER_GAME):
            await self._run_question(room)
        await self.emit(
            "game_ended",
            {"leaderboard": self._leaderboard(room), "winner": self._leaderboard(room)[0] if room.players else None},
            room.id,
        )
        for sid in list(room.players):
            self.sid_to_room.pop(sid, None)
        self.rooms.pop(room.id, None)

    async def _run_question(self, room: GameRoom) -> None:
        room.question_number += 1
        question = self.store.get_question(room.category, room.difficulty, room.used_question_ids)
        room.used_question_ids.add(question.id)
        options, correct_option_id = shuffled_options(question)
        timer = question_timer(question.difficulty)
        room.current = CurrentQuestion(question, options, correct_option_id, timer, time.monotonic())
        for player in room.players.values():
            player.double_active = False

        await self.emit(
            "question_started",
            {
                "questionNumber": room.question_number,
                "totalQuestions": QUESTIONS_PER_GAME,
                "question": question.text,
                "difficulty": question.difficulty,
                "timer": timer,
                "options": options,
                "leaderboard": self._leaderboard(room),
            },
            room.id,
        )

        for bot_id, player in list(room.players.items()):
            if player.is_bot:
                asyncio.create_task(self._bot_answer(room, bot_id, timer, question.difficulty))

        await asyncio.sleep(timer)
        await self._end_question(room)

    async def _end_question(self, room: GameRoom) -> None:
        current = room.current
        if not current:
            return
        correct_humans = 0
        human_count = 0
        for player_id, player in room.players.items():
            if player.is_bot:
                continue
            human_count += 1
            if current.answers.get(player_id, AnswerRecord("", 0, False, 0)).correct:
                correct_humans += 1

        previous_difficulty = room.difficulty
        room.difficulty = adapt_difficulty(room.difficulty, correct_humans, human_count)
        await self.emit(
            "question_ended",
            {
                "correctOptionId": current.correct_option_id,
                "correctAnswer": current.question.correct_answer,
                "answers": {
                    pid: {
                        "nickname": room.players[pid].nickname,
                        "correct": answer.correct,
                        "points": answer.points,
                        "responseTime": round(answer.response_time, 2),
                    }
                    for pid, answer in current.answers.items()
                    if pid in room.players
                },
                "leaderboard": self._leaderboard(room),
                "nextDifficulty": room.difficulty,
                "previousDifficulty": previous_difficulty,
            },
            room.id,
        )
        room.current = None
        await asyncio.sleep(2)

    async def _bot_answer(self, room: GameRoom, bot_id: str, timer: int, difficulty: int) -> None:
        await asyncio.sleep(random.uniform(max(2.0, timer * 0.25), timer * 0.92))
        if room.current is None or bot_id not in room.players:
            return
        correct_chance = max(0.25, 0.9 - difficulty * 0.06)
        if random.random() < correct_chance:
            option_id = room.current.correct_option_id
        else:
            wrong = [o["id"] for o in room.current.options if o["id"] != room.current.correct_option_id]
            option_id = random.choice(wrong)
        self._record_answer(room, bot_id, option_id, time.monotonic())
        await self.emit("scoreboard_update", {"leaderboard": self._leaderboard(room)}, room.id)

    def _record_answer(self, room: GameRoom, player_id: str, option_id: str, answered_at: float) -> AnswerRecord | None:
        current = room.current
        if not current or player_id in current.answers:
            return None
        player = room.players[player_id]
        response_time = max(0.0, min(current.timer, answered_at - current.started_at))
        correct = option_id == current.correct_option_id
        points_possible = BASE_POINTS * (2 if player.double_active else 1)
        points = calculate_points(response_time, current.timer, points_possible, correct)
        player.score += points
        record = AnswerRecord(option_id, response_time, correct, points)
        current.answers[player_id] = record
        return record

    def _resolve_category(self, room: GameRoom) -> str:
        votes = [vote for pid, vote in room.category_votes.items() if pid in room.players and not room.players[pid].is_bot]
        if not votes:
            return "Mixed"
        counts = Counter(votes)
        top_count = max(counts.values())
        winners = [category for category, count in counts.items() if count == top_count]
        return winners[0] if len(winners) == 1 else "Mixed"

    def _room_for_sid(self, sid: str) -> GameRoom | None:
        return self.rooms.get(self.sid_to_room.get(sid, ""))

    def _unique_nickname(self, nickname: str) -> str:
        names = {p.nickname for p in self.waiting.values()}
        for room in self.rooms.values():
            names.update(p.nickname for p in room.players.values())
        if nickname not in names:
            return nickname
        for idx in range(2, 100):
            candidate = f"{nickname}{idx}"
            if candidate not in names:
                return candidate
        return f"{nickname}{random.randint(100, 999)}"

    def _players_payload(self, room: GameRoom) -> list[dict[str, Any]]:
        return [{"id": p.id, "nickname": p.nickname, "isBot": p.is_bot} for p in room.players.values()]

    def _leaderboard(self, room: GameRoom) -> list[dict[str, Any]]:
        ranked = sorted(room.players.values(), key=lambda player: player.score, reverse=True)
        return [
            {"rank": idx + 1, "id": player.id, "nickname": player.nickname, "score": player.score, "isBot": player.is_bot}
            for idx, player in enumerate(ranked)
        ]

    def _vote_payload(self, room: GameRoom) -> dict[str, Any]:
        return {
            "seconds": CATEGORY_SECONDS,
            "categories": list(CATEGORY_MAP),
            "votes": dict(Counter(room.category_votes.values())),
            "players": self._players_payload(room),
        }

    async def _emit_lobby_update(self) -> None:
        names = [player.nickname for player in self.waiting.values()]
        await self.emit(
            "lobby_update",
            {"players": names, "count": len(names), "seconds": MATCHMAKING_SECONDS},
            None,
        )

    def _make_bots(self) -> list[Player]:
        names = ["Quizzy", "Captain Guess", "Fact Phantom", "Drama Llama", "Map Master"]
        return [
            Player(id=f"bot-{int(time.time() * 1000)}-{idx}", nickname=name, is_bot=True)
            for idx, name in enumerate(random.sample(names, random.randint(1, 3)), start=1)
        ]


def calculate_points(response_time: float, question_timer_value: int, points_possible: int, correct: bool) -> int:
    if not correct:
        return 0
    ratio = max(0.0, min(1.0, response_time / question_timer_value))
    return round((1 - (ratio / 2)) * points_possible)


def adapt_difficulty(current: int, correct_humans: int, human_count: int) -> int:
    if human_count and correct_humans > human_count / 2:
        return min(10, current + 1)
    return current


def bot_answer_delay(timer: int, rng: random.Random | None = None) -> float:
    rng = rng or random
    return rng.uniform(max(2.0, timer * 0.25), timer * 0.92)


def bot_correct_answer(difficulty: int, rng: random.Random | None = None) -> bool:
    rng = rng or random
    return rng.random() < max(0.25, 0.9 - difficulty * 0.06)


def _clean(value: str, limit: int = 32) -> str:
    return html.escape(str(value).strip()[:limit], quote=False)
