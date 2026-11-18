const $ = (sel) => document.querySelector(sel);
const STORAGE_KEY = "edge-ai-sessions-v1";

const state = {
  sessions: [],
  currentId: null,
  streaming: false,
  controller: null,
};

const messagesEl = $("#messages");
const inputEl = $("#input");
const sendBtn = $("#sendBtn");
const sessionListEl = $("#sessionList");
const panelLogEl = $("#panelLog");

function uid() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
}

function loadSessions() {
  try {
    state.sessions = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    if (!Array.isArray(state.sessions)) state.sessions = [];
  } catch {
    state.sessions = [];
  }
  if (!state.sessions.length) {
    const s = { id: uid(), title: "新对话", messages: [], createdAt: Date.now() };
    state.sessions = [s];
    state.currentId = s.id;
    saveSessions();
  } else {
    state.currentId = state.sessions[0].id;
  }
  renderSessions();
  renderMessages();
}

function saveSessions() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.sessions));
}

function currentSession() {
  return state.sessions.find((s) => s.id === state.currentId) || state.sessions[0];
}

function renderSessions() {
  sessionListEl.innerHTML = "";
  state.sessions.forEach((s) => {
    const el = document.createElement("div");
    el.className = "session-item" + (s.id === state.currentId ? " active" : "");
    el.textContent = s.title || "新对话";
    el.title = s.title || "新对话";
    el.onclick = () => {
      state.currentId = s.id;
      renderSessions();
      renderMessages();
    };
    sessionListEl.appendChild(el);
  });
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderMarkdown(raw) {
  let text = String(raw || "");
  const codeBlocks = [];
  text = text.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (_m, _lang, code) => {
    const idx = codeBlocks.length;
    codeBlocks.push("<pre><code>" + escapeHtml(code) + "</code></pre>");
    return `@@CODE${idx}@@`;
  });

  text = escapeHtml(text)
    .replace(/^### (.*)$/gm, "<h3>$1</h3>")
    .replace(/^## (.*)$/gm, "<h2>$1</h2>")
    .replace(/^# (.*)$/gm, "<h1>$1</h1>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/^- (.*)$/gm, "<li>$1</li>")
    .replace(/\n/g, "<br>");

  text = text.replace(/@@CODE(\d+)@@/g, (_m, idx) => codeBlocks[Number(idx)] || "");
  return text || "<p>（空）</p>";
}

function messageNode(msg) {
  const wrap = document.createElement("div");
  wrap.className = "msg " + (msg.role === "user" ? "user" : "assistant");

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = msg.role === "user" ? "你" : "AI";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = renderMarkdown(msg.content);
  if (msg.image) {
    const img = document.createElement("img");
    img.src = msg.image;
    img.alt = "uploaded";
    bubble.appendChild(img);
  }

  wrap.appendChild(avatar);
  wrap.appendChild(bubble);
  return wrap;
}

function renderMessages() {
  const session = currentSession();
  messagesEl.innerHTML = "";
  if (!session || !session.messages.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.innerHTML = `
      <h1>本地多模态 AI 终端</h1>
      <p>树莓派 4B · Qwen2.5-0.5B · STM32G431</p>
      <p>试试：让 LED1 亮起来 / 在 LCD 上显示 Hello / 读取 ADC</p>
    `;
    messagesEl.appendChild(empty);
    return;
  }
  session.messages.forEach((m) => messagesEl.appendChild(messageNode(m)));
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addMessage(role, content, image) {
  const session = currentSession();
  if (!session) return null;
  const msg = { role, content, image: image || null };
  session.messages.push(msg);
  if (role === "user" && (!session.title || session.title === "新对话")) {
    session.title = content.slice(0, 24) || "新对话";
  }
  saveSessions();
  renderSessions();
  messagesEl.appendChild(messageNode(msg));
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return msg;
}

function logPanel(text) {
  const line = `[${new Date().toLocaleTimeString()}] ${text}`;
  panelLogEl.textContent = (line + "\n" + panelLogEl.textContent).slice(0, 2000);
}

async function deviceFetch(path, options) {
  const resp = await fetch(path, options);
  const data = await resp.json().catch(() => ({}));
  logPanel(`${path} -> ${resp.status} ${JSON.stringify(data)}`);
  return data;
}

async function sendMessage() {
  if (state.streaming) {
    state.controller?.abort();
    return;
  }
  const text = inputEl.value.trim();
  if (!text) return;

  addMessage("user", text);
  inputEl.value = "";
  autoResize();

  const session = currentSession();
  const history = session.messages
    .filter((m) => m.content && !(m.role === "assistant" && !m.content))
    .slice(-12)
    .map((m) => ({ role: m.role, content: m.content }));

  const assistant = { role: "assistant", content: "" };
  session.messages.push(assistant);
  const node = messageNode(assistant);
  messagesEl.appendChild(node);
  const bubble = node.querySelector(".bubble");
  bubble.classList.add("typing");

  state.streaming = true;
  sendBtn.disabled = false;
  state.controller = new AbortController();

  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: state.controller.signal,
      body: JSON.stringify({ messages: history, max_tokens: 192, temperature: 0.7 }),
    });
    if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop() || "";
      for (const part of parts) {
        const line = part.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        const data = line.slice(6);
        if (data === "[DONE]") continue;
        try {
          const json = JSON.parse(data);
          if (json.error) {
            assistant.content += `\n\n> 错误：${json.error}`;
          } else {
            assistant.content += json.choices?.[0]?.delta?.content || "";
          }
        } catch {
          /* ignore partial JSON */
        }
        bubble.innerHTML = renderMarkdown(assistant.content);
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }
    }
  } catch (err) {
    if (err.name !== "AbortError") {
      assistant.content += `\n\n> 请求失败：${err.message}`;
    }
  } finally {
    bubble.classList.remove("typing");
    bubble.innerHTML = renderMarkdown(assistant.content || "（无响应）");
    state.streaming = false;
    state.controller = null;
    sendBtn.disabled = false;
    saveSessions();
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }
}

function autoResize() {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + "px";
}

async function refreshStatus() {
  try {
    const resp = await fetch("/api/device/status");
    const data = await resp.json();
    const ok = !!data.open;
    ["#serialDot", "#panelDot"].forEach((sel) => {
      const el = $(sel);
      if (el) el.className = "dot " + (ok ? "ok" : "bad");
    });
    const text = ok ? `串口已连接 · ${data.port}` : `串口未连接 · ${data.last_error || "未打开"}`;
    $("#serialText").textContent = text;
    $("#panelStatus").textContent = text;
  } catch {
    $("#serialText").textContent = "后端未连接";
    $("#panelStatus").textContent = "后端未连接";
  }
}

/* ---------- events ---------- */
sendBtn.addEventListener("click", sendMessage);

inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});
inputEl.addEventListener("input", autoResize);

$("#newChat").addEventListener("click", () => {
  const s = { id: uid(), title: "新对话", messages: [], createdAt: Date.now() };
  state.sessions.unshift(s);
  state.currentId = s.id;
  saveSessions();
  renderSessions();
  renderMessages();
  inputEl.focus();
});

$("#clearChat").addEventListener("click", () => {
  const session = currentSession();
  if (!session) return;
  session.messages = [];
  session.title = "新对话";
  saveSessions();
  renderSessions();
  renderMessages();
});

document.querySelectorAll("[data-led]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    await deviceFetch("/api/device/led", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: Number(btn.dataset.led), on: btn.dataset.on === "1" }),
    });
  });
});

$("#lcdSend").addEventListener("click", async () => {
  await deviceFetch("/api/device/lcd", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ line: 1, text: $("#lcdText").value || "Hello" }),
  });
});

$("#lcdClear").addEventListener("click", async () => {
  await deviceFetch("/api/device/lcd/clear", { method: "POST" });
});

$("#adcRead").addEventListener("click", async () => {
  const data = await deviceFetch("/api/device/adc");
  $("#adcValue").textContent = data.raw ?? "--";
});

const pwmRange = $("#pwmRange");
pwmRange.addEventListener("input", () => {
  $("#pwmValue").textContent = pwmRange.value + "%";
});

$("#pwmApply").addEventListener("click", async () => {
  await deviceFetch("/api/device/pwm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ch: 1, duty: Number(pwmRange.value) }),
  });
});

$("#imageBtn").addEventListener("click", () => $("#imageInput").click());
$("#imageInput").addEventListener("change", (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    addMessage("user", "（已选择图片，VLM 图片问答将在 M5 接入）", reader.result);
    inputEl.focus();
  };
  reader.readAsDataURL(file);
  e.target.value = "";
});

loadSessions();
refreshStatus();
setInterval(refreshStatus, 5000);
