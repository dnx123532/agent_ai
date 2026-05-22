// ============================================================
// frontend/app.js
// JARVIS V5 — Chat UI logic
// WebSocket / SSE streaming + markdown rendering
// ============================================================

const API_BASE   = "";          // Same origin
const CHAT_URL   = `${API_BASE}/chat`;
const STATUS_URL = `${API_BASE}/status`;

// ── DOM Elements ─────────────────────────────────────────────
const chatArea    = document.getElementById("chat-area");
const userInput   = document.getElementById("user-input");
const sendBtn     = document.getElementById("send-btn");
const statusDot   = document.getElementById("status-dot");
const statusLabel = document.getElementById("status-label");
const modelLabel  = document.getElementById("model-label");

let isProcessing = false;

// ════════════════════════════════════════════════════════════
// STATUS CHECK
// ════════════════════════════════════════════════════════════

async function checkStatus() {
  try {
    const resp = await fetch(STATUS_URL, { signal: AbortSignal.timeout(5000) });
    if (!resp.ok) throw new Error("Server tidak merespons");

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
  } catch (e) {
    statusDot.classList.remove("online");
    statusLabel.textContent = "Offline";
    modelLabel.textContent  = "—";
  }
}

// Cek status saat load dan tiap 30 detik
checkStatus();
setInterval(checkStatus, 30000);

// ════════════════════════════════════════════════════════════
// MARKDOWN RENDERER (lightweight)
// ════════════════════════════════════════════════════════════

function renderMarkdown(text) {
  if (!text) return "";

  let html = escapeHtml(text);

  // Code block (``` ... ```) — proses sebelum inline
  html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const langLabel = lang ? `<span class="code-lang">${lang}</span>` : "";
    return `<pre>${langLabel}<code>${code.trim()}</code></pre>`;
  });

  // Inline code
  html = html.replace(/`([^`\n]+?)`/g, "<code>$1</code>");

  // Headings
  html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.+)$/gm,  "<h2>$1</h2>");
  html = html.replace(/^# (.+)$/gm,   "<h1>$1</h1>");

  // Bold & italic
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
  html = html.replace(/\*\*(.+?)\*\*/g,     "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g,         "<em>$1</em>");

  // Links
  html = html.replace(/\[(.+?)\]\((.+?)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>');

  // Tables
  html = html.replace(/((?:\|.+\|\n?)+)/g, (block) => {
    const lines = block.trim().split("\n").filter(l => l.trim());
    if (lines.length < 2) return block;

    // Cek apakah baris ke-2 adalah separator (|---|---|)
    const isSep = (l) => /^\|[\s\-:|]+\|$/.test(l.trim());

    let tableHtml = "<table>";
    let inBody = false;

    lines.forEach((line, i) => {
      if (isSep(line)) { inBody = true; return; }

      const cells = line.trim().replace(/^\||\|$/g, "").split("|");
      const tag   = (i === 0 && !inBody) ? "th" : "td";

      tableHtml += "<tr>" + cells.map(c =>
        `<${tag}>${c.trim()}</${tag}>`
      ).join("") + "</tr>";
    });

    tableHtml += "</table>";
    return tableHtml;
  });

  // Unordered list
  html = html.replace(/^[ \t]*[-*] (.+)$/gm, "<li>$1</li>");
  html = html.replace(/(<li>.*<\/li>\n?)+/g, m => `<ul>${m}</ul>`);

  // Ordered list
  html = html.replace(/^\d+\. (.+)$/gm, "<li>$1</li>");

  // Horizontal rule
  html = html.replace(/^---$/gm, "<hr>");

  // Line breaks — dua newline = paragraf baru
  html = html.replace(/\n\n+/g, "</p><p>");
  html = html.replace(/\n/g, "<br>");

  return `<p>${html}</p>`;
}

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ════════════════════════════════════════════════════════════
// MESSAGE RENDERING
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
  return msg;
}

function addTypingIndicator() {
  const indicator = document.createElement("div");
  indicator.className = "message assistant";
  indicator.id = "typing-indicator";
  indicator.innerHTML = `
    <div class="avatar">J</div>
    <div class="typing-indicator">
      <div class="typing-dots">
        <span></span><span></span><span></span>
      </div>
      <span class="typing-label" id="typing-label">Thinking...</span>
    </div>
  `;
  chatArea.appendChild(indicator);
  scrollToBottom();
  return indicator;
}

function updateTypingLabel(text) {
  const label = document.getElementById("typing-label");
  if (label) label.textContent = text;
}

function removeTypingIndicator() {
  const indicator = document.getElementById("typing-indicator");
  if (indicator) indicator.remove();
}

function addAssistantMessage(text, steps = []) {
  const msg = document.createElement("div");
  msg.className = "message assistant";

  // Bangun steps HTML
  let stepsHtml = "";
  if (steps.length > 0) {
    const stepItems = steps.map(step => buildStepHtml(step)).join("");
    stepsHtml = `
      <div class="steps-container">
        <button class="steps-toggle" onclick="toggleSteps(this)">
          <span>⚡ ${steps.length} Langkah</span>
          <span class="arrow">▼</span>
        </button>
        <div class="steps-body">${stepItems}</div>
      </div>
    `;
  }

  msg.innerHTML = `
    <div class="avatar">J</div>
    <div>
      ${stepsHtml}
      <div class="bubble">${renderMarkdown(text)}</div>
    </div>
  `;

  chatArea.appendChild(msg);
  scrollToBottom();
  return msg;
}

function buildStepHtml(step) {
  const type    = step.type || "THINK";
  const badge   = type;
  let   content = "";

  if (type === "THINK") {
    content = `<span class="step-content">${escapeHtml(step.thought || "")}</span>`;
    if (step.action && step.action !== "final_answer") {
      content += ` → <span class="step-tool">${escapeHtml(step.action)}</span>`;
    }
  } else if (type === "ACT") {
    content = `<span class="step-content">🔧 <span class="step-tool">${escapeHtml(step.tool || "")}</span>(${escapeHtml(JSON.stringify(step.input || {}).slice(0, 120))})</span>`;
  } else if (type === "OBS") {
    const res = typeof step.result === "string" ? step.result : JSON.stringify(step.result);
    content = `<span class="step-content">${escapeHtml(res.slice(0, 400))}</span>`;
  } else if (type === "ANSWER") {
    content = `<span class="step-content">✅ Selesai</span>`;
  }

  return `
    <div class="step-item ${type}">
      <span class="step-badge">${badge}</span>
      ${content}
    </div>
  `;
}

function toggleSteps(btn) {
  btn.classList.toggle("open");
  const body = btn.nextElementSibling;
  body.classList.toggle("open");
}

function addErrorMessage(text) {
  const msg = document.createElement("div");
  msg.className = "message assistant";
  msg.innerHTML = `
    <div class="avatar">J</div>
    <div class="error-message">⚠️ ${escapeHtml(text)}</div>
  `;
  chatArea.appendChild(msg);
  scrollToBottom();
}

function scrollToBottom() {
  chatArea.scrollTop = chatArea.scrollHeight;
}

// ════════════════════════════════════════════════════════════
// SEND MESSAGE — SSE STREAMING
// ════════════════════════════════════════════════════════════

async function sendMessage() {
  const text = userInput.value.trim();
  if (!text || isProcessing) return;

  // Hapus welcome screen jika ada
  const welcome = document.querySelector(".welcome");
  if (welcome) welcome.remove();

  // Tambahkan pesan user
  addUserMessage(text);
  userInput.value = "";
  autoResize(userInput);

  // Disable input
  isProcessing = true;
  sendBtn.disabled   = true;
  sendBtn.classList.add("loading");
  sendBtn.textContent = "...";
  userInput.disabled = true;

  // Tampilkan typing indicator
  addTypingIndicator();

  const collectedSteps = [];
  let   finalAnswer    = "";
  let   errorOccurred  = false;

  try {
    const resp = await fetch(CHAT_URL, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ message: text, stream: true }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ error: `HTTP ${resp.status}` }));
      throw new Error(err.error || `Server error ${resp.status}`);
    }

    // Baca SSE stream
    const reader  = resp.body.getReader();
    const decoder = new TextDecoder();
    let   buffer  = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop(); // Sisa yang belum lengkap

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;

        const jsonStr = line.slice(6).trim();
        if (!jsonStr) continue;

        let event;
        try {
          event = JSON.parse(jsonStr);
        } catch {
          continue;
        }

        const type = event.type;

        if (type === "THINK") {
          updateTypingLabel(`💭 Thinking... (step ${event.step})`);
          collectedSteps.push({
            step:         event.step,
            type:         "THINK",
            thought:      event.thought,
            action:       event.action,
            action_input: event.action_input,
          });
        } else if (type === "ACT") {
          updateTypingLabel(`🔧 Running: ${event.tool}...`);
          collectedSteps.push({
            step:  event.step,
            type:  "ACT",
            tool:  event.tool,
            input: event.input,
          });
        } else if (type === "OBS") {
          updateTypingLabel(`👁️ Observing...`);
          collectedSteps.push({
            step:   event.step,
            type:   "OBS",
            tool:   event.tool,
            result: event.result,
          });
        } else if (type === "done") {
          finalAnswer = event.answer || "";
        } else if (type === "error") {
          throw new Error(event.message);
        }
      }
    }

  } catch (err) {
    errorOccurred = true;
    removeTypingIndicator();
    addErrorMessage(`Gagal berkomunikasi dengan JARVIS: ${err.message}`);
    console.error("Chat error:", err);
  }

  if (!errorOccurred) {
    removeTypingIndicator();
    if (finalAnswer) {
      addAssistantMessage(finalAnswer, collectedSteps);
    } else {
      addErrorMessage("JARVIS tidak mengembalikan jawaban.");
    }
  }

  // Re-enable input
  isProcessing        = false;
  sendBtn.disabled    = false;
  sendBtn.classList.remove("loading");
  sendBtn.textContent = "SEND";
  userInput.disabled  = false;
  userInput.focus();

  // Update status setelah selesai
  checkStatus();
}

// ════════════════════════════════════════════════════════════
// INPUT HANDLING
// ════════════════════════════════════════════════════════════

function autoResize(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = Math.min(textarea.scrollHeight, 160) + "px";
}

userInput.addEventListener("input", () => autoResize(userInput));

userInput.addEventListener("keydown", (e) => {
  // Enter kirim, Shift+Enter newline
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

sendBtn.addEventListener("click", sendMessage);

// ── Hint chips ────────────────────────────────────────────────
document.querySelectorAll(".hint-chip").forEach(chip => {
  chip.addEventListener("click", () => {
    userInput.value = chip.dataset.query || chip.textContent.replace(/^[^\s]+\s/, "");
    userInput.focus();
    autoResize(userInput);
  });
});

// ── Focus input saat load ─────────────────────────────────────
userInput.focus();
