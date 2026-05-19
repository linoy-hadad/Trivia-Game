from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass
from pathlib import Path


CATEGORY_MAP = {
    "Mixed": None,
    "Israel politics and wars": "Israel politics and Wars in israel",
    "Celebs Drama": "celebs dramas",
    "Music": "music",
    "Geography": "geography questions",
}


@dataclass(frozen=True)
class Question:
    id: int
    text: str
    answers: tuple[str, str, str, str]
    correct_answer: str
    difficulty: int
    classification: str


class QuestionStore:
    def __init__(self, db_path: str | Path = "trivia.db") -> None:
        self.db_path = Path(db_path)

    def get_question(
        self,
        category: str,
        target_difficulty: int,
        used_question_ids: set[int] | None = None,
    ) -> Question:
        used_question_ids = used_question_ids or set()
        target_difficulty = max(1, min(10, int(target_difficulty)))
        candidates = self._load_candidates(category, used_question_ids)
        if not candidates:
            candidates = self._load_candidates(category, set())
        if not candidates:
            raise ValueError(f"No questions found for category {category!r}")

        nearest_distance = min(abs(q.difficulty - target_difficulty) for q in candidates)
        nearest = [q for q in candidates if abs(q.difficulty - target_difficulty) == nearest_distance]
        return random.choice(nearest)

    def _load_candidates(self, category: str, used_question_ids: set[int]) -> list[Question]:
        db_category = CATEGORY_MAP.get(category)
        params: list[object] = []
        where = []
        if db_category:
            where.append("classification = ?")
            params.append(db_category)
        if used_question_ids:
            placeholders = ",".join("?" for _ in used_question_ids)
            where.append(f"rowid NOT IN ({placeholders})")
            params.extend(sorted(used_question_ids))

        sql = (
            'SELECT rowid, Question, "answer 1", "answer 2", "answer 3", "answer 4", '
            'Difficulty, classification FROM questions'
        )
        if where:
            sql += " WHERE " + " AND ".join(where)

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(sql, params).fetchall()

        return [
            Question(
                id=int(row[0]),
                text=str(row[1]),
                answers=(str(row[2]), str(row[3]), str(row[4]), str(row[5])),
                correct_answer=str(row[5]),
                difficulty=int(row[6]),
                classification=str(row[7]),
            )
            for row in rows
        ]


def question_timer(difficulty: int) -> int:
    if difficulty <= 3:
        return 10
    if difficulty <= 7:
        return 15
    return 20


def shuffled_options(question: Question) -> tuple[list[dict[str, str]], str]:
    indexed = [
        {"id": f"{question.id}-{idx}", "text": answer, "is_correct": answer == question.correct_answer}
        for idx, answer in enumerate(question.answers)
    ]
    random.shuffle(indexed)
    correct_option_id = next(option["id"] for option in indexed if option["is_correct"])
    public_options = [{"id": option["id"], "text": option["text"]} for option in indexed]
    return public_options, correct_option_id
