const $ = (sel) => document.querySelector(sel);
const STORAGE_KEY = "edge-ai-sessions-v1";

const state = {
  sessions: [],
  currentId: null,
  streaming: false,
  controller: null,
  pendingImage: null,
};

const guideState = {
  module: null,
  code: "",
  actionCode: "",
  copyTimer: null,
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
    el.title = s.title || "新对话";

    const title = document.createElement("span");
    title.className = "session-title";
    title.textContent = s.title || "新对话";

    const del = document.createElement("button");
    del.type = "button";
    del.className = "session-del";
    del.textContent = "×";
    del.title = "删除这个对话";
    del.setAttribute("aria-label", "删除这个对话");
    del.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteSession(s.id);
    });

    el.appendChild(title);
    el.appendChild(del);
    el.onclick = () => {
      state.currentId = s.id;
      renderSessions();
      renderMessages();
    };
    sessionListEl.appendChild(el);
  });
  const clearAll = $("#clearAllHistory");
  if (clearAll) {
    clearAll.hidden = !(state.sessions.length > 1 || state.sessions.some((s) => s.messages.length));
  }
}

function deleteSession(id) {
  const target = state.sessions.find((s) => s.id === id);
  if (!target) return;
  const name = target.title || "新对话";
  if (!window.confirm(`删除对话“${name}”？此操作不可撤销。`)) return;

  state.sessions = state.sessions.filter((s) => s.id !== id);
  if (!state.sessions.length) {
    const s = { id: uid(), title: "新对话", messages: [], createdAt: Date.now() };
    state.sessions = [s];
    state.currentId = s.id;
  } else if (state.currentId === id) {
    state.currentId = state.sessions[0].id;
  }
  saveSessions();
  renderSessions();
  renderMessages();
}

function clearAllHistory() {
  if (!window.confirm("清空全部历史对话？此操作不可撤销。")) return;
  const s = { id: uid(), title: "新对话", messages: [], createdAt: Date.now() };
  state.sessions = [s];
  state.currentId = s.id;
  saveSessions();
  renderSessions();
  renderMessages();
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

/* ---------- AI 对话 / 代码讲解 视图切换 ---------- */
function setView(view) {
  const next = view === "guide" ? "guide" : "chat";
  $("#chatView").hidden = next !== "chat";
  $("#guideView").hidden = next !== "guide";
  document.querySelectorAll(".view-tab").forEach((tab) => {
    const active = tab.dataset.view === next;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", active ? "true" : "false");
  });
  if (next === "chat") {
    requestAnimationFrame(() => messagesEl.scrollTop = messagesEl.scrollHeight);
  } else {
    $("#guideView").scrollTop = 0;
  }
}

function copyGuideCode(button) {
  const text = guideState.code || "";
  if (!text) return;
  const done = () => {
    const old = button.textContent;
    button.textContent = "已复制";
    clearTimeout(guideState.copyTimer);
    guideState.copyTimer = setTimeout(() => { button.textContent = old; }, 1200);
  };
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(done).catch(() => {});
    return;
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand("copy"); done(); } catch (e) {}
  ta.remove();
}

function openGuide(module, detail = "", ctx = {}) {
  const guide = window.CODE_GUIDES && window.CODE_GUIDES[module];
  if (!guide) return;
  guideState.module = module;
  guideState.code = guide.build ? guide.build(ctx) : guide.code;
  guideState.actionCode = guide.action ? guide.action(ctx) : "";

  $("#guideKicker").textContent = `${guide.kicker} · 控制代码讲解`;
  $("#guideTitle").textContent = guide.title;
  $("#guideSummary").textContent = detail ? `${detail} ｜ ${guide.summary}` : guide.summary;
  $("#guideActionLabel").textContent = ctx.action ? "对应本次操作" : "示例";
  $("#guideActionCode").textContent = guideState.actionCode || "/* 本模块没有单独的操作片段 */";
  $("#guideSteps").innerHTML = guide.steps.map(([title, body]) => `
    <li>
      <div class="guide-step-title">${escapeHtml(title)}</div>
      <p>${escapeHtml(body)}</p>
    </li>
  `).join("");
  $("#guideFiles").innerHTML = guide.files
    .map((file) => `<code>${escapeHtml(file)}</code>`)
    .join("");
  $("#guideCode").textContent = guideState.code;
  $("#guideEmpty").hidden = true;
  $("#guideContent").hidden = false;
  $("#guideCopy").hidden = false;
  setView("guide");
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

const KIND_LABEL = {
  board: "板卡实测",
  code: "源码",
  ioc: "CubeMX",
  ppt: "课件",
  pdf: "文档",
  xlsx: "考点统计",
  docx: "真题目录",
  exam_ocr: "真题 OCR",
};

function sourceNode(source) {
  const details = document.createElement("details");
  details.className = "source-item";

  const summary = document.createElement("summary");
  const n = document.createElement("span");
  n.className = "source-n";
  n.textContent = `[${source.n || "?"}]`;
  const label = document.createElement("span");
  label.textContent = source.label || source.title || "资料";
  const kind = document.createElement("span");
  kind.className = "source-kind";
  kind.textContent = KIND_LABEL[source.kind] || source.kind || "资料";
  summary.appendChild(n);
  summary.appendChild(label);
  summary.appendChild(kind);

  const snippet = document.createElement("p");
  snippet.className = "source-snippet";
  snippet.textContent = source.snippet || "";
  const path = document.createElement("div");
  path.className = "source-path";
  path.textContent = source.source || "";

  details.appendChild(summary);
  details.appendChild(snippet);
  details.appendChild(path);
  return details;
}

function sourcesNode(sources, knowledge, mode) {
  const wrap = document.createElement("div");
  wrap.className = "sources";
  const head = document.createElement("div");
  head.className = "sources-head";
  const hits = sources?.length || 0;
  const total = knowledge?.chunks ? ` · 知识库 ${knowledge.chunks} 片段` : "";
  const modeLabel = mode === "knowledge" ? "知识库直答 · " : mode === "rag" ? "RAG 生成 · " : "";
  head.innerHTML = `${escapeHtml(modeLabel)}参考资料 <b>${hits}</b> 条${escapeHtml(total)}`;
  wrap.appendChild(head);
  (sources || []).forEach((s) => wrap.appendChild(sourceNode(s)));
  return wrap;
}

function thinkingHtml(msg) {
  const modelMode = msg.mode === "rag" || msg.mode === "llm";
  const elapsed = msg.startedAt ? Math.max(0, Math.floor((Date.now() - msg.startedAt) / 1000)) : 0;
  const label = modelMode ? "本地模型思考中" : "正在检索资料";
  const wait = elapsed ? ` 已等待 ${elapsed}s` : "";
  const note = modelMode
    ? "1.5B 本地模型可能需要 40–120 秒，请稍候"
    : "知识库直答通常 1 秒内完成";
  return `<p class="thinking">${label}…${wait}<br><span>${note}</span></p>`;
}

function renderAssistantInto(bubble, msg) {
  bubble.innerHTML = msg.content ? renderMarkdown(msg.content) : thinkingHtml(msg);
  if (msg.sources?.length) {
    bubble.appendChild(sourcesNode(msg.sources, msg.knowledge, msg.mode));
  }
}

function messageNode(msg) {
  const wrap = document.createElement("div");
  wrap.className = "msg " + (msg.role === "user" ? "user" : "assistant");

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = msg.role === "user" ? "你" : "蓝";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (msg.role === "assistant") {
    renderAssistantInto(bubble, msg);
  } else {
    bubble.innerHTML = renderMarkdown(msg.content);
  }
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
      <h1>蓝桥杯嵌入式 AI 助教</h1>
      <p>专精 CT117E-M4 · STM32G431RBT6 · 本地知识库 + 本地模型</p>
      <p>从引脚、外设、代码到历年真题，按“结论 → 步骤 → 易错点”回答。</p>
      <div class="quick-grid">
        <button data-quick="CT117E-M4 怎么快速入门？"><span>入门路线</span>CT117E-M4 怎么快速入门？</button>
        <button data-quick="LED 怎么点亮？PC8–PC15 和 PD2 怎么配置？"><span>GPIO / LED</span>LED 怎么点亮？PC8–PC15 和 PD2 怎么配置？</button>
        <button data-quick="USART1 串口怎么配置？为什么收不到数据？"><span>串口</span>USART1 串口怎么配置？为什么收不到数据？</button>
        <button data-quick="LCD 怎么显示字符串？"><span>LCD</span>LCD 怎么显示字符串？</button>
        <button data-quick="PWM 怎么输出 1kHz、50% 占空比？"><span>TIM / PWM</span>PWM 怎么输出 1kHz、50% 占空比？</button>
        <button data-quick="I2C 读写 AT24C02 怎么写？"><span>I2C / EEPROM</span>I2C 读写 AT24C02 怎么写？</button>
        <button data-quick="省赛真题一般考哪些模块？"><span>备考</span>省赛真题一般考哪些模块？</button>
        <button data-quick="按键消抖和松手检测怎么写？"><span>按键</span>按键消抖和松手检测怎么写？</button>
      </div>
      <p class="empty-note">也可以直接说“让 LED1 亮起来”“在 LCD 上显示 Hello”，助手会执行硬件命令。</p>
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
  messagesEl.querySelector(".empty")?.remove();
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

function clearPendingImage() {
  state.pendingImage = null;
  const preview = $("#imagePreview");
  const img = $("#imagePreviewImg");
  if (preview) preview.hidden = true;
  if (img) img.src = "";
}

async function sendVision() {
  const dataUrl = state.pendingImage;
  if (!dataUrl || state.streaming) return;

  const text = inputEl.value.trim();
  const prompt = text || "请描述这张图片";
  addMessage("user", prompt, dataUrl);
  clearPendingImage();
  inputEl.value = "";
  autoResize();

  const session = currentSession();
  const assistant = { role: "assistant", content: "" };
  session.messages.push(assistant);
  const node = messageNode(assistant);
  messagesEl.appendChild(node);
  const bubble = node.querySelector(".bubble");
  bubble.classList.add("typing");

  state.streaming = true;
  sendBtn.disabled = false;

  try {
    const blob = await (await fetch(dataUrl)).blob();
    const form = new FormData();
    form.append("file", blob, "upload.jpg");
    form.append("prompt", prompt);
    const resp = await fetch("/api/vision", { method: "POST", body: form });
    const data = await resp.json().catch(() => ({}));
    assistant.content = data.response || data.detail || "VLM 无响应";
  } catch (err) {
    assistant.content = `图片请求失败：${err.message}`;
  } finally {
    bubble.classList.remove("typing");
    bubble.innerHTML = renderMarkdown(assistant.content);
    state.streaming = false;
    sendBtn.disabled = false;
    saveSessions();
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }
}

async function sendMessage() {
  if (state.streaming) {
    state.controller?.abort();
    return;
  }
  if (state.pendingImage) {
    await sendVision();
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

  const assistant = {
    role: "assistant",
    content: "",
    sources: [],
    knowledge: null,
    mode: null,
    startedAt: Date.now(),
  };
  session.messages.push(assistant);
  const node = messageNode(assistant);
  messagesEl.appendChild(node);
  const bubble = node.querySelector(".bubble");
  bubble.classList.add("typing");

  state.streaming = true;
  sendBtn.disabled = false;
  state.controller = new AbortController();

  const thinkingTimer = setInterval(() => {
    if (assistant.content) return;
    const p = bubble.querySelector(".thinking");
    if (p) p.outerHTML = thinkingHtml(assistant);
  }, 1000);

  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: state.controller.signal,
      body: JSON.stringify({
        messages: history,
        max_tokens: 192,
        temperature: 0.3,
        use_knowledge: true,
      }),
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
          if (json.sources) {
            assistant.sources = json.sources;
            assistant.knowledge = json.knowledge || assistant.knowledge;
            assistant.mode = json.mode || assistant.mode;
            saveSessions();
          }
          if (json.error) {
            assistant.content += `\n\n> 错误：${json.error}`;
          } else {
            assistant.content += json.choices?.[0]?.delta?.content || "";
          }
        } catch {
          /* ignore partial JSON */
        }
        renderAssistantInto(bubble, assistant);
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }
    }
  } catch (err) {
    if (err.name !== "AbortError") {
      assistant.content += `\n\n> 请求失败：${err.message}`;
    }
  } finally {
    clearInterval(thinkingTimer);
    bubble.classList.remove("typing");
    if (!assistant.content) assistant.content = "（无响应）";
    renderAssistantInto(bubble, assistant);
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
    const access = $("#accessUrl");
    if (access && data.access_url) {
      access.href = data.access_url;
      access.textContent = `其他电脑访问：${data.access_url}`;
    }
  } catch {
    $("#serialText").textContent = "后端未连接";
    $("#panelStatus").textContent = "后端未连接";
  }
}

async function refreshKnowledge() {
  try {
    const resp = await fetch("/api/knowledge/status");
    const data = await resp.json();
    const ok = !!data.loaded && data.chunks > 0;
    const pill = $("#kbPill");
    const panel = $("#kbStatus");
    const foot = $("#kbFoot");
    if (pill) {
      pill.textContent = ok
        ? `知识库 ${data.chunks} 片段`
        : (data.error ? "知识库未加载" : "知识库加载中…");
      pill.className = "kb-pill" + (ok ? "" : " bad");
    }
    if (panel) {
      panel.textContent = ok
        ? `已加载 ${data.chunks} 个片段 · ${data.sources} 个来源 · 支持板卡、引脚、代码与真题检索`
        : (data.error || "知识库加载中…");
    }
    if (foot) {
      foot.textContent = ok
        ? `本地知识库 · ${data.chunks} 片段 / ${data.sources} 来源`
        : "本地知识库未加载";
    }
  } catch {
    const pill = $("#kbPill");
    if (pill) {
      pill.textContent = "知识库离线";
      pill.className = "kb-pill bad";
    }
  }
}

/* ---------- events ---------- */
document.querySelectorAll(".view-tab").forEach((tab) => {
  tab.addEventListener("click", () => setView(tab.dataset.view));
});
$("#guideBack").addEventListener("click", () => setView("chat"));
$("#guideCopy").addEventListener("click", (e) => copyGuideCode(e.currentTarget));
$("#guideCopy2").addEventListener("click", (e) => copyGuideCode(e.currentTarget));
document.querySelectorAll("[data-guide]").forEach((btn) => {
  btn.addEventListener("click", () => openGuide(btn.dataset.guide, "预览"));
});

messagesEl.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-quick]");
  if (!btn || state.streaming) return;
  inputEl.value = btn.dataset.quick || "";
  autoResize();
  sendMessage();
});

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
  setView("chat");
  inputEl.focus();
});

$("#clearAllHistory").addEventListener("click", clearAllHistory);

$("#clearChat").addEventListener("click", () => {
  const session = currentSession();
  if (!session) return;
  session.messages = [];
  session.title = "新对话";
  saveSessions();
  renderSessions();
  renderMessages();
});

const ledState = new Set();
let ledSeq = 0;

function renderLedState() {
  let mask = 0;
  document.querySelectorAll("#ledSelect option").forEach((opt) => {
    const id = Number(opt.value);
    const on = ledState.has(id);
    opt.textContent = `LD${id}${on ? " ●" : ""}`;
    if (on) mask |= 1 << (id - 1);
  });
  $("#ledMask").textContent = mask.toString(16).toUpperCase().padStart(2, "0");
}

function applyLedStates(states) {
  ledState.clear();
  Object.entries(states || {}).forEach(([id, on]) => {
    if (on) ledState.add(Number(id));
  });
  renderLedState();
}

async function refreshLeds() {
  const seq = ++ledSeq;
  try {
    const data = await deviceFetch("/api/device/leds");
    if (data.ok && seq === ledSeq) applyLedStates(data.states);
  } catch (err) {
    logPanel(`LED 回读失败：${err.message}`);
  }
}

async function setLed(id, on) {
  const seq = ++ledSeq;
  try {
    const data = await deviceFetch("/api/device/led", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, on }),
    });
    if (data.ok && data.states && seq === ledSeq) {
      // Derive the before/after masks from the device response, not from a
      // possibly stale UI state after page reload.
      let afterMask = 0;
      Object.entries(data.states).forEach(([ledId, value]) => {
        if (value) afterMask |= 1 << (Number(ledId) - 1);
      });
      const bit = 1 << (id - 1);
      const beforeMask = on ? (afterMask & ~bit) : (afterMask | bit);
      applyLedStates(data.states);
      openGuide("led", `刚执行：LED ${id} → ${on ? "亮" : "灭"}`, {
        action: "led", id, on, beforeMask,
      });
    }
  } catch (err) {
    logPanel(`LED${id} 失败：${err.message}`);
  }
}

async function setAllLeds(mask) {
  const seq = ++ledSeq;
  try {
    const data = await deviceFetch("/api/device/ledall", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mask }),
    });
    if (data.ok && data.states && seq === ledSeq) {
      applyLedStates(data.states);
      openGuide("led", `刚执行：LEDALL 0x${Number(mask).toString(16).toUpperCase().padStart(2, "0")}`, {
        action: "all", mask,
      });
    }
  } catch (err) {
    logPanel(`LED 全控失败：${err.message}`);
  }
}

$("#ledOn").addEventListener("click", () => setLed(Number($("#ledSelect").value), true));
$("#ledOff").addEventListener("click", () => setLed(Number($("#ledSelect").value), false));
$("#ledAllOn").addEventListener("click", () => setAllLeds(0xff));
$("#ledAllOff").addEventListener("click", () => setAllLeds(0x00));
$("#ledRefresh").addEventListener("click", refreshLeds);

$("#lcdSend").addEventListener("click", async () => {
  const text = $("#lcdText").value || "Hello";
  const data = await deviceFetch("/api/device/lcd", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ line: 1, text }),
  });
  if (data.ok) openGuide("lcd", `刚执行：LCD 1 "${text}"`, { action: "lcd", text });
});

$("#lcdClear").addEventListener("click", async () => {
  const data = await deviceFetch("/api/device/lcd/clear", { method: "POST" });
  if (data.ok) openGuide("lcd", "刚执行：LCDCLR 清屏", { action: "lcd_clear" });
});

let adcBusy = false;

async function readAdc(ch, silent = false) {
  if (adcBusy) return;
  adcBusy = true;
  try {
    const data = silent
      ? await (await fetch(`/api/device/adc?ch=${ch}`)).json()
      : await deviceFetch(`/api/device/adc?ch=${ch}`);
    if (data.ok) {
      $(`#adc${ch}Value`).textContent = data.raw;
      $(`#adc${ch}Voltage`).textContent = Number(data.voltage).toFixed(3) + " V";
      if (!silent) {
        openGuide("adc", `刚读取：ADC${ch} = ${data.raw}（${Number(data.voltage).toFixed(3)} V）`, {
          action: "adc", ch, raw: data.raw, voltage: data.voltage,
        });
      }
    }
  } catch (err) {
    if (!silent) logPanel(`ADC${ch} 读取失败：${err.message}`);
  } finally {
    adcBusy = false;
  }
}

async function readAllAdc(silent = false) {
  await readAdc(1, silent);
  await readAdc(2, silent);
}

$("#adc1Read").addEventListener("click", () => readAdc(1, false));
$("#adc2Read").addEventListener("click", () => readAdc(2, false));
$("#adcAuto").addEventListener("change", (e) => {
  if (e.target.checked) readAllAdc(true);
});

const pwm1Range = $("#pwm1Range");
const pwm2Range = $("#pwm2Range");
let pwmSeq = 0;

function setPwmUi(ch, duty) {
  const value = Math.max(0, Math.min(100, Number(duty) || 0));
  const range = ch === 1 ? pwm1Range : pwm2Range;
  range.value = String(value);
  $(`#pwm${ch}Value`).textContent = value + "%";
  $("#pwmSummary").textContent = `${pwm1Range.value}% / ${pwm2Range.value}%`;
}

async function writePwm(ch, duty) {
  return deviceFetch("/api/device/pwm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ch, duty }),
  });
}

async function applyBothPwm() {
  const seq = ++pwmSeq;
  const d1 = Number(pwm1Range.value);
  const d2 = Number(pwm2Range.value);
  try {
    const r1 = await writePwm(1, d1);
    const r2 = await writePwm(2, d2);
    if (seq !== pwmSeq) return;
    if (r1.ok) setPwmUi(1, r1.duty);
    if (r2.ok) setPwmUi(2, r2.duty);
    $("#pwmReadback").textContent = `回读 ${r1.duty ?? "--"}% / ${r2.duty ?? "--"}%`;
    if (r1.ok && r2.ok) {
      openGuide("pwm", `刚设置：PWM1=${r1.duty}% · PWM2=${r2.duty}%`, {
        action: "pwm", duty1: r1.duty, duty2: r2.duty,
      });
    }
  } catch (err) {
    logPanel(`PWM 设置失败：${err.message}`);
  }
}

async function readPwm() {
  const seq = ++pwmSeq;
  try {
    const r1 = await deviceFetch("/api/device/pwm");
    const r2 = await deviceFetch("/api/device/pwm2");
    if (seq !== pwmSeq) return;
    if (r1.ok) setPwmUi(1, r1.duty);
    if (r2.ok) setPwmUi(2, r2.duty);
    $("#pwmReadback").textContent = `回读 ${r1.duty ?? "--"}% / ${r2.duty ?? "--"}%`;
  } catch (err) {
    logPanel(`PWM 回读失败：${err.message}`);
  }
}

pwm1Range.addEventListener("input", () => {
  $("#pwm1Value").textContent = pwm1Range.value + "%";
  $("#pwmSummary").textContent = `${pwm1Range.value}% / ${pwm2Range.value}%`;
});
pwm2Range.addEventListener("input", () => {
  $("#pwm2Value").textContent = pwm2Range.value + "%";
  $("#pwmSummary").textContent = `${pwm1Range.value}% / ${pwm2Range.value}%`;
});

$("#pwmApply").addEventListener("click", applyBothPwm);
$("#pwmRead").addEventListener("click", readPwm);

$("#imageBtn").addEventListener("click", () => $("#imageInput").click());
$("#imageInput").addEventListener("change", (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    state.pendingImage = reader.result;
    $("#imagePreviewImg").src = reader.result;
    $("#imagePreview").hidden = false;
    inputEl.focus();
  };
  reader.readAsDataURL(file);
  e.target.value = "";
});
$("#imageClear").addEventListener("click", clearPendingImage);

const THEME_KEY = "ai-terminal-theme-v1";
const THEMES = ["light", "mint", "warm", "lavender", "dark"];

function applyTheme(theme) {
  const value = THEMES.includes(theme) ? theme : "light";
  document.documentElement.dataset.theme = value;
  const select = $("#themeSelect");
  if (select) select.value = value;
  try {
    localStorage.setItem(THEME_KEY, value);
  } catch {
    /* private mode / storage disabled */
  }
}

const themeSelect = $("#themeSelect");
if (themeSelect) {
  let saved = "light";
  try {
    saved = localStorage.getItem(THEME_KEY) || document.documentElement.dataset.theme || "light";
  } catch {
    saved = document.documentElement.dataset.theme || "light";
  }
  applyTheme(saved);
  themeSelect.addEventListener("change", (e) => applyTheme(e.target.value));
}

loadSessions();
refreshStatus();
refreshKnowledge();
refreshLeds()
  .then(() => readPwm())
  .then(() => readAllAdc(true))
  .then(() => {
    setTimeout(() => {
      if ($("#pwmReadback")?.textContent === "--") readPwm();
      if ($("#adc1Value")?.textContent === "--" || $("#adc2Value")?.textContent === "--") readAllAdc(true);
    }, 1200);
  });
setInterval(refreshStatus, 5000);
setInterval(refreshKnowledge, 30000);
setInterval(() => {
  if ($("#adcAuto")?.checked) readAllAdc(true);
}, 1500);
