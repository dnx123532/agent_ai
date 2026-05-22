// ============================================================
// frontend/app.js — JARVIS V5
// WebSocket client dengan real-time token streaming
// Typewriter effect — token muncul satu per satu
// ============================================================

const WS_URL     = `ws://${location.host}/ws`;
const STATUS_URL = "/status";

// ── DOM ──────────────────────────────────────────────────────
const chatArea    = document.getElementById("chat-area");
const userInput   = document.getElementById("user-input");
const sendBtn     = document.getElementById("send-btn");
const statusDot   = document.getElementById("status-dot");
const statusLabel = document.getElementById("status-label");
const modelLabel  = document.getElementById("model-label");

// ── State ────────────────────────────────────────────────────
let ws            = null;
let isProcessing  = false;
let currentBubble = null;   // Bubble sedang diisi token
let currentSteps  = [];     // Steps yang dikumpulkan
let stepContainer = null;   // Container steps untuk update

// ════════════════════════════════════════════════════════════
// WEBSOCKET
// ════════════════════════════════════════════════════════════

function connectWS() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;

  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    console.log("[WS] Connected to JARVIS");
    statusDot.classList.add("online");
    statusLabel.textContent = "Online";
  };

  ws.onclose = () => {
    console.log("[WS] Disconnected, reconnecting in 2s...");
    statusDot.classList.remove("online");
    statusLabel.textContent = "Reconnecting...";
    setTimeout(connectWS, 2000);
  };

  ws.onerror = (e) => {
    console.error("[WS] Error:", e);
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      handleEvent(data);
    } catch (e) {
      console.error("[WS] Parse error:", e);
    }
  };
}

// ════════════════════════════════════════════════════════════
// EVENT HANDLER — proses setiap event dari server
// ════════════════════════════════════════════════════════════

function handleEvent(data) {
  const type = data.type;

  if (type === "ping") return;

  if (type === "thinking") {
    // Server mulai thinking untuk step ini
    updateTypingLabel(`Thinking... (step ${data.step})`);
    return;
  }

  if (type === "step") {
    handleStep(data);
    return;
  }

  if (type === "token") {
    // Token final answer — append ke bubble langsung
    appendToken(data.content);
    return;
  }

  if (type === "done") {
    finishResponse(data.total_steps || 0);
    return;
  }

  if (type === "error") {
    removeTypingIndicator();
    addErrorMessage(data.message || "Terjadi kesalahan.");
    resetInput();
    return;
  }
}

function handleStep(data) {
  const st = data.step_type;

  if (st === "THINK") {
    const action = data.action || "";
    if (action && action !== "final_answer") {
      updateTypingLabel(`Calling: ${action}...`);
    } else {
      updateTypingLabel("Writing answer...");
    }
    currentSteps.push({
      step: data.step, type: "THINK",
      thought: data.thought, action: action,
      action_input: data.action_input,
    });
  } else if (st === "ACT") {
    updateTypingLabel(`Running tool: ${data.tool}...`);
    currentSteps.push({
      step: data.step, type: "ACT",
      tool: data.tool, input: data.input,
    });
  } else if (st === "OBS") {
    updateTypingLabel("Observing result...");
    currentSteps.push({
      step: data.step, type: "OBS",
      tool: data.tool, result: data.result,
    });
  }

  // Update steps panel di DOM
  if (stepContainer) {
    refreshStepsPanel();
  }
}

// ════════════════════════════════════════════════════════════
// SEND MESSAGE
// ════════════════════════════════════════════════════════════

function sendMessage() {
  const text = userInput.value.trim();
  if (!text || isProcessing) return;

  if (!ws || ws.readyState !== WebSocket.OPEN) {
    addErrorMessage("WebSocket tidak terkoneksi. Tunggu sebentar lalu coba lagi.");
    return;
  }

  // Hapus welcome screen
  const welcome = document.querySelector(".welcome");
  if (welcome) welcome.remove();

  // Tampilkan pesan user
  addUserMessage(text);
  userInput.value = "";
  autoResize(userInput);

  // Lock input
  isProcessing    = true;
  sendBtn.disabled   = true;
  sendBtn.classList.add("loading");
  sendBtn.textContent = "...";
  userInput.disabled = true;

  // Reset state
  currentSteps  = [];
  currentBubble = null;
  stepContainer = null;

  // Buat message bubble kosong untuk JARVIS (akan diisi token)
  createAssistantBubble();

  // Tambahkan typing indicator
  showTypingIndicator();

  // Kirim ke server via WebSocket
  ws.send(JSON.stringify({ message: text }));
}

// ════════════════════════════════════════════════════════════
// DOM BUILDERS
// ════════════════════════════════════════════════════════════

function addUserMessage(text) {
  const msg = document.createElement("div");
  msg.className = "message user";
  msg.innerHTML = `
    <div class="avatar">U</div>
    <div class="bubble">${escapeHtml(text)}</div>
  `;
  chatArea.appendChild(msg);
  scrollToBottom();
}

function createAssistantBubble() {
  // Buat container message JARVIS
  const msg = document.createElement("div");
  msg.className = "message assistant";
  msg.id = "jarvis-response";

  // Steps panel (kosong dulu, akan di-update)
  const stepsDiv = document.createElement("div");
  stepsDiv.id = "live-steps";
  stepsDiv.className = "steps-container";
  stepsDiv.style.display = "none";

  // Bubble teks (akan diisi token)
  const bubble = document.createElement("div");
  bubble.className = "bubble streaming";
  bubble.id = "streaming-bubble";

  msg.appendChild(stepsDiv);
  msg.appendChild(bubble);
  chatArea.appendChild(msg);

  currentBubble = bubble;
  stepContainer = stepsDiv;

  scrollToBottom();
}

function showTypingIndicator() {
  if (currentBubble) {
    currentBubble.innerHTML = `
      <div class="typing-indicator" id="typing-indicator">
        <div class="typing-dots">
          <span></span><span></span><span></span>
        </div>
        <span class="typing-label" id="typing-label">Connecting...</span>
      </div>
    `;
  }
}

function updateTypingLabel(text) {
  const el = document.getElementById("typing-label");
  if (el) el.textContent = text;
}

function removeTypingIndicator() {
  const ind = document.getElementById("typing-indicator");
  if (ind) ind.remove();
}

// Append token ke bubble — efek typewriter
let rawAnswer = "";
function appendToken(token) {
  if (!currentBubble) return;

  // Hapus typing indicator saat token pertama tiba
  removeTypingIndicator();

  rawAnswer += token;

  // Render markdown setiap kali token baru masuk
  currentBubble.innerHTML = renderMarkdown(rawAnswer) + '<span class="cursor">|</span>';
  scrollToBottom();
}

function finishResponse(totalSteps) {
  // Render final markdown tanpa cursor
  if (currentBubble && rawAnswer) {
    currentBubble.innerHTML = renderMarkdown(rawAnswer);
    currentBubble.classList.remove("streaming");
  }

  removeTypingIndicator();

  // Update steps panel final
  if (stepContainer && currentSteps.length > 0) {
    stepContainer.style.display = "block";
    refreshStepsPanel();
  }

  rawAnswer = "";
  resetInput();
  checkStatus();
}

function refreshStepsPanel() {
  if (!stepContainer || currentSteps.length === 0) return;

  const stepItems = currentSteps.map(buildStepHtml).join("");
  const count     = currentSteps.length;

  stepContainer.innerHTML = `
    <button class="steps-toggle" onclick="toggleSteps(this)">
      <span>⚡ ${count} Langkah</span>
      <span class="arrow">▼</span>
    </button>
    <div class="steps-body">${stepItems}</div>
  `;
}

function buildStepHtml(step) {
  const type = step.type || "THINK";
  let content = "";

  if (type === "THINK") {
    const thought = escapeHtml(step.thought || "");
    const action  = step.action && step.action !== "final_answer"
      ? ` <span class="step-tool">→ ${escapeHtml(step.action)}</span>` : "";
    content = `<span class="step-content">${thought}${action}</span>`;
  } else if (type === "ACT") {
    const inp = typeof step.input === "string"
      ? step.input : JSON.stringify(step.input || {});
    content = `<span class="step-content">
      <span class="step-tool">${escapeHtml(step.tool || "")}</span>
      <span style="color:var(--text-muted)">(${escapeHtml(inp.slice(0, 100))})</span>
    </span>`;
  } else if (type === "OBS") {
    const res = String(step.result || "").slice(0, 300);
    content = `<span class="step-content">${escapeHtml(res)}</span>`;
  }

  return `
    <div class="step-item ${type}">
      <span class="step-badge">${type}</span>
      ${content}
    </div>
  `;
}

function addErrorMessage(text) {
  const msg = document.createElement("div");
  msg.className = "message assistant";
  msg.innerHTML = `
    <div class="avatar">J</div>
    <div class="error-message">⚠ ${escapeHtml(text)}</div>
  `;
  chatArea.appendChild(msg);
  scrollToBottom();
}

function toggleSteps(btn) {
  btn.classList.toggle("open");
  btn.nextElementSibling.classList.toggle("open");
}

function resetInput() {
  isProcessing        = false;
  sendBtn.disabled    = false;
  sendBtn.classList.remove("loading");
  sendBtn.textContent = "SEND";
  userInput.disabled  = false;
  userInput.focus();
}

function scrollToBottom() {
  chatArea.scrollTop = chatArea.scrollHeight;
}

// ════════════════════════════════════════════════════════════
// STATUS CHECK
// ════════════════════════════════════════════════════════════

async function checkStatus() {
  try {
    const resp = await fetch(STATUS_URL, { signal: AbortSignal.timeout(5000) });
    const data = await resp.json();
    if (data.ollama_running) {
      statusDot.classList.add("online");
      statusLabel.textContent = "Online";
      modelLabel.textContent  = data.active_model || "N/A";
    } else {
      statusDot.classList.remove("online");
      statusLabel.textContent = "Ollama Offline";
      modelLabel.textContent  = "—";
    }
  } catch {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      statusDot.classList.remove("online");
      statusLabel.textContent = "Offline";
      modelLabel.textContent  = "—";
    }
  }
}

checkStatus();
setInterval(checkStatus, 30000);

// ════════════════════════════════════════════════════════════
// MARKDOWN RENDERER
// ════════════════════════════════════════════════════════════

function renderMarkdown(text) {
  if (!text) return "";
  let html = escapeHtml(text);

  // Code block
  html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const label = lang ? `<span class="code-lang">${lang}</span>` : "";
    return `<pre>${label}<code>${code.trim()}</code></pre>`;
  });

  // Inline code
  html = html.replace(/`([^`\n]+?)`/g, "<code>$1</code>");

  // Headings
  html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.+)$/gm,  "<h2>$1</h2>");
  html = html.replace(/^# (.+)$/gm,   "<h1>$1</h1>");

  // Bold / italic
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");

  // Links
  html = html.replace(/\[(.+?)\]\((.+?)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>');

  // Table
  html = html.replace(/((?:\|.+\|\n?)+)/g, block => {
    const lines = block.trim().split("\n").filter(l => l.trim());
    if (lines.length < 2) return block;
    const isSep = l => /^\|[\s\-:|]+\|$/.test(l.trim());
    let out = "<table>", head = true;
    lines.forEach((line, i) => {
      if (isSep(line)) { head = false; return; }
      const cells = line.trim().replace(/^\||\|$/g, "").split("|");
      const tag   = (i === 0 && head) ? "th" : "td";
      out += "<tr>" + cells.map(c => `<${tag}>${c.trim()}</${tag}>`).join("") + "</tr>";
    });
    return out + "</table>";
  });

  // List
  html = html.replace(/^[ \t]*[-*] (.+)$/gm, "<li>$1</li>");
  html = html.replace(/(<li>.*<\/li>\n?)+/g, m => `<ul>${m}</ul>`);
  html = html.replace(/^\d+\. (.+)$/gm, "<li>$1</li>");

  // HR
  html = html.replace(/^---$/gm, "<hr>");

  // Paragraphs
  html = html.replace(/\n\n+/g, "</p><p>");
  html = html.replace(/\n/g, "<br>");

  return `<p>${html}</p>`;
}

function escapeHtml(t) {
  return String(t)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ════════════════════════════════════════════════════════════
// INPUT HANDLING
// ════════════════════════════════════════════════════════════

function autoResize(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 160) + "px";
}

userInput.addEventListener("input", () => autoResize(userInput));
userInput.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
sendBtn.addEventListener("click", sendMessage);

// Hint chips
document.querySelectorAll(".hint-chip").forEach(chip => {
  chip.addEventListener("click", () => {
    userInput.value = chip.dataset.query || chip.textContent.trim();
    userInput.focus();
    autoResize(userInput);
  });
});

// ── Inisialisasi WebSocket ────────────────────────────────────
connectWS();
userInput.focus();
