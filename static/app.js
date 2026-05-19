const socket = io();

const joinPanel = document.querySelector("#joinPanel");
const gamePanel = document.querySelector("#gamePanel");
const joinForm = document.querySelector("#joinForm");
const nicknameInput = document.querySelector("#nicknameInput");
const phaseLabel = document.querySelector("#phaseLabel");
const mainTitle = document.querySelector("#mainTitle");
const timerBox = document.querySelector("#timerBox");
const lobbyView = document.querySelector("#lobbyView");
const lobbyText = document.querySelector("#lobbyText");
const lobbyPlayers = document.querySelector("#lobbyPlayers");
const categoryView = document.querySelector("#categoryView");
const categoryGrid = document.querySelector("#categoryGrid");
const voteSummary = document.querySelector("#voteSummary");
const questionView = document.querySelector("#questionView");
const questionCounter = document.querySelector("#questionCounter");
const questionText = document.querySelector("#questionText");
const answers = document.querySelector("#answers");
const feedback = document.querySelector("#feedback");
const leaderboard = document.querySelector("#leaderboard");
const finalView = document.querySelector("#finalView");
const chatForm = document.querySelector("#chatForm");
const chatInput = document.querySelector("#chatInput");
const chatLog = document.querySelector("#chatLog");
const emojiRow = document.querySelector("#emojiRow");
const playAgainBtn = document.querySelector("#playAgainBtn");
const scoreboardModal = document.querySelector("#scoreboardModal");
const scoreboardCloseBtn = document.querySelector("#scoreboardCloseBtn");
const winnerCaption = document.querySelector("#winnerCaption");
const finalScoreboard = document.querySelector("#finalScoreboard");
const answerPopup = document.querySelector("#answerPopup");

let countdownInterval = null;
let answered = false;
let hiddenOptions = new Set();
let lastAnswerResult = null;
let popupTimeout = null;

const helpButtons = {
  fifty_fifty: document.querySelector("#fiftyBtn"),
  call_friend: document.querySelector("#friendBtn"),
  double_score: document.querySelector("#doubleBtn"),
};

["😀", "😂", "🔥", "👏", "🤯", "😎", "💀", "🎉", "❤️", "👍"].forEach((emoji) => {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "emoji-button";
  button.textContent = emoji;
  button.addEventListener("click", () => socket.emit("emoji", { emoji }));
  emojiRow.appendChild(button);
});

joinForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const nickname = nicknameInput.value.trim();
  if (!nickname) return;
  socket.emit("join", { nickname });
  joinPanel.classList.add("hidden");
  gamePanel.classList.remove("hidden");
  setPageState("lobby");
  showOnly(lobbyView);
});

Object.entries(helpButtons).forEach(([helpType, button]) => {
  button.addEventListener("click", () => socket.emit("use_help", { helpType }));
});

chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = chatInput.value.trim();
  if (!message) return;
  socket.emit("chat_message", { message });
  chatInput.value = "";
});

scoreboardCloseBtn.addEventListener("click", () => {
  scoreboardModal.classList.add("hidden");
});

playAgainBtn.addEventListener("click", resetToJoin);

socket.on("lobby_update", (data) => {
  setPageState("lobby");
  phaseLabel.textContent = "Lobby";
  mainTitle.textContent = "Waiting for players";
  lobbyText.textContent = `${data.count} player${data.count === 1 ? "" : "s"} ${data.count === 1 ? "is" : "are"} in the game.`;
  lobbyPlayers.innerHTML = "";
  data.players.forEach((name) => lobbyPlayers.appendChild(chip(name)));
  startCountdown(data.seconds || 30);
});

socket.on("category_vote_started", (data) => {
  setPageState("lobby");
  showOnly(categoryView);
  phaseLabel.textContent = "Category";
  mainTitle.textContent = "Pick the match category";
  startCountdown(data.seconds || 15);
  categoryGrid.innerHTML = "";
  data.categories.forEach((category) => {
    const button = document.createElement("button");
    button.className = "category-card";
    button.type = "button";
    button.textContent = category;
    button.addEventListener("click", () => socket.emit("vote_category", { category }));
    categoryGrid.appendChild(button);
  });
  renderVotes(data.votes || {});
});

socket.on("category_vote_update", (data) => renderVotes(data.votes || {}));

socket.on("game_started", (data) => {
  setPageState("question");
  showOnly(questionView);
  phaseLabel.textContent = data.category;
  mainTitle.textContent = "Answer the question";
  renderLeaderboard(data.leaderboard || []);
});

socket.on("question_started", (data) => {
  setPageState("question");
  showOnly(questionView);
  answered = false;
  hiddenOptions = new Set();
  lastAnswerResult = null;
  hideAnswerPopup();
  feedback.textContent = "";
  mainTitle.textContent = "Choose your answer";
  questionText.textContent = data.question;
  questionCounter.textContent = `Question ${data.questionNumber} / ${data.totalQuestions}`;
  startCountdown(data.timer);
  renderAnswers(data.options);
  renderLeaderboard(data.leaderboard || []);
});

socket.on("answer_result", (data) => {
  lastAnswerResult = data;
});

socket.on("help_result", (data) => {
  if (data.error) {
    feedback.textContent = data.error;
  }
  if (data.removeOptionIds) {
    data.removeOptionIds.forEach((id) => hiddenOptions.add(id));
    document.querySelectorAll(".answer-button").forEach((button) => {
      if (hiddenOptions.has(button.dataset.optionId)) button.classList.add("removed");
    });
    feedback.textContent = "Two wrong answers removed.";
  }
  if (data.message) feedback.textContent = data.message;
  if (data.helps) updateHelps(data.helps);
});

socket.on("question_ended", (data) => {
  stopCountdown();
  document.querySelectorAll(".answer-button").forEach((button) => {
    button.disabled = true;
    if (button.dataset.optionId === data.correctOptionId) button.classList.add("correct", "blink-correct");
  });
  feedback.textContent = "";
  if (lastAnswerResult) {
    showAnswerPopup(lastAnswerResult.correct ? "Correct!" : "Not this time!");
  }
  renderLeaderboard(data.leaderboard || []);
});

socket.on("scoreboard_update", (data) => renderLeaderboard(data.leaderboard || []));

socket.on("game_ended", (data) => {
  setPageState("final");
  showOnly(finalView);
  phaseLabel.textContent = "Final";
  mainTitle.textContent = "Game over";
  timerBox.textContent = "0";
  renderLeaderboard(data.leaderboard || []);
  renderFinalScoreboard(data.leaderboard || [], data.winner);
  scoreboardModal.classList.remove("hidden");
});

socket.on("chat_message", (data) => addChatLine(`${data.nickname}: ${data.message}`));
socket.on("emoji", (data) => addChatLine(`${data.nickname}: ${data.emoji}`));
socket.on("error_message", (data) => {
  feedback.textContent = data.message || "Something went wrong.";
});

function renderAnswers(options) {
  answers.innerHTML = "";
  Object.values(helpButtons).forEach((button) => {
    button.disabled = false;
    button.classList.remove("used");
  });
  options.forEach((option) => {
    const button = document.createElement("button");
    button.className = "answer-button";
    button.type = "button";
    button.dataset.optionId = option.id;
    button.textContent = option.text;
    button.addEventListener("click", () => {
      if (answered) return;
      answered = true;
      button.classList.add("selected");
      document.querySelectorAll(".answer-button").forEach((item) => (item.disabled = true));
      socket.emit("submit_answer", { optionId: option.id });
    });
    answers.appendChild(button);
  });
}

function updateHelps(helps) {
  Object.entries(helps).forEach(([helpType, available]) => {
    if (helpButtons[helpType]) {
      helpButtons[helpType].disabled = !available;
      helpButtons[helpType].classList.toggle("used", !available);
    }
  });
}

function renderVotes(votes) {
  const parts = Object.entries(votes).map(([category, count]) => `${category}: ${count}`);
  voteSummary.textContent = parts.length ? parts.join(" | ") : "No votes yet.";
}

function renderLeaderboard(rows) {
  leaderboard.innerHTML = "";
  rows.forEach((row) => {
    const item = document.createElement("li");
    item.innerHTML = `<span>${row.rank}. ${row.nickname}</span><strong>${row.score}</strong>`;
    leaderboard.appendChild(item);
  });
}

function renderFinalScoreboard(rows, winner) {
  const sortedRows = [...rows].sort((a, b) => b.score - a.score);
  const winnerName = winner?.nickname || sortedRows[0]?.nickname || "Nobody";
  winnerCaption.textContent = `${winnerName} is the winner!`;
  finalScoreboard.innerHTML = "";
  sortedRows.forEach((row, index) => {
    const item = document.createElement("li");
    item.innerHTML = `<span class="rank">${index + 1}</span><span>${row.nickname}</span><strong>${row.score}</strong>`;
    finalScoreboard.appendChild(item);
  });
}

function showOnly(view) {
  [lobbyView, categoryView, questionView, finalView].forEach((element) => element.classList.add("hidden"));
  view.classList.remove("hidden");
}

function setPageState(state) {
  document.body.classList.remove("state-join", "state-lobby", "state-question", "state-final");
  document.body.classList.add(`state-${state}`);
}

function resetToJoin() {
  stopCountdown();
  hideAnswerPopup();
  lastAnswerResult = null;
  setPageState("join");
  joinPanel.classList.remove("hidden");
  gamePanel.classList.add("hidden");
  scoreboardModal.classList.add("hidden");
  showOnly(lobbyView);
  nicknameInput.value = "";
  chatInput.value = "";
  chatLog.innerHTML = "";
  leaderboard.innerHTML = "";
  finalScoreboard.innerHTML = "";
  feedback.textContent = "";
  answers.innerHTML = "";
  lobbyPlayers.innerHTML = "";
  lobbyText.textContent = "Matchmaking is open.";
  phaseLabel.textContent = "Lobby";
  mainTitle.textContent = "Waiting for players";
  timerBox.textContent = "30";
}

function showAnswerPopup(message) {
  hideAnswerPopup();
  answerPopup.textContent = message;
  answerPopup.classList.remove("hidden");
  popupTimeout = window.setTimeout(hideAnswerPopup, 2000);
}

function hideAnswerPopup() {
  if (popupTimeout) {
    window.clearTimeout(popupTimeout);
    popupTimeout = null;
  }
  answerPopup.classList.add("hidden");
  answerPopup.textContent = "";
}

function chip(text) {
  const element = document.createElement("span");
  element.className = "chip";
  element.textContent = text;
  return element;
}

function addChatLine(text) {
  const line = document.createElement("div");
  line.className = "chat-line";
  line.textContent = text;
  chatLog.appendChild(line);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function startCountdown(seconds) {
  stopCountdown();
  let remaining = seconds;
  timerBox.textContent = remaining;
  countdownInterval = window.setInterval(() => {
    remaining = Math.max(0, remaining - 1);
    timerBox.textContent = remaining;
    if (remaining <= 0) stopCountdown();
  }, 1000);
}

function stopCountdown() {
  if (countdownInterval) {
    window.clearInterval(countdownInterval);
    countdownInterval = null;
  }
}
