# Trivia Arena

Trivia Arena is a real-time multiplayer trivia game built with FastAPI, Socket.IO, and a browser-based frontend. Players join with a nickname, vote for a category, answer timed questions, use special helpers, chat during the game, and compete for the top spot on the live leaderboard.

## Features

- Real-time multiplayer gameplay with Socket.IO
- Solo play support with bot players when only one human joins
- Category voting before the game starts
- 10 timed trivia questions per game
- Adaptive difficulty that increases when players perform well
- Speed-based scoring with a live leaderboard
- Final Challenge vote after the main round
- Three one-time helpers:
  - `50/50` removes two wrong answers
  - `Call Friend` gives playful AI-style advice
  - `Double` doubles the score for the current question
- In-game chat and emoji reactions
- Sound effects, background music, and custom visual assets
- Local SQLite question database

## Tech Stack

- Python
- FastAPI
- python-socketio
- Uvicorn
- SQLite
- HTML, CSS, and JavaScript
- Optional OpenAI/Pydantic AI integration for the `Call Friend` helper

## Project Structure

```text
.
+-- server.py                  # FastAPI and Socket.IO app entry point
+-- game_engine.py             # Main game logic, scoring, bots, timers, and events
+-- question_store.py          # SQLite question loading and option shuffling
+-- llm_help.py                # Optional AI helper for "Call Friend"
+-- create_db.py               # Optional CSV-to-SQLite conversion script
+-- trivia.db                  # Local trivia question database
+-- trivia_questions_250.csv   # Source trivia questions
+-- requirements.txt           # Python dependencies
+-- static/
|   +-- index.html             # Game UI
|   +-- app.js                 # Frontend Socket.IO logic
|   +-- styles.css             # Styling
|   +-- assets/                # Images, fonts, and sounds
+-- tests/                     # Test files
```

## Setup

1. Create and activate a virtual environment:

```powershell
python -m venv venv
venv\Scripts\activate
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Run the app:

```powershell
uvicorn server:app --host 127.0.0.1 --port 8007
```

4. Open the game in your browser:

```text
http://127.0.0.1:8007
```

To test multiplayer locally, open the same URL in multiple browser tabs or windows.

## Optional AI Helper

The game works without an API key. If no key is configured, `Call Friend` uses built-in fallback advice.

To enable the AI-powered helper, create a `.env` file or set these environment variables:

```env
OPENAI_API_KEY=your_api_key_here
PYDANTIC_AI_MODEL=openai:gpt-5.5
```

`PYDANTIC_AI_MODEL` is optional. If it is not set, the project uses the default model defined in `llm_help.py`.

## Game Flow

1. Players enter a nickname and join the lobby.
2. After matchmaking, players vote for a trivia category.
3. The game asks 10 timed questions.
4. Correct answers earn points based on speed.
5. Players can use each helper once per game.
6. After the main round, players vote on whether to play the Final Challenge.
7. The final scoreboard announces the winner.

## Question Data

The app reads questions from `trivia.db`. The included database is already ready to use.

If you want to regenerate the database from `trivia_questions_250.csv`, install `pandas` and run:

```powershell
pip install pandas
python create_db.py
```

## Running Tests

```powershell
pytest
```

## Notes

- The server serves the frontend from the `static/` folder.
- Matchmaking waits briefly before starting a room.
- If only one human player joins, the game adds bot players automatically.
- The app is intended for local development and classroom/demo use.
