/* ── Step 3: Character Maker Chat ──────────── */

import { t, getLocale } from "../setup.js";

let templates = [];
let selectedTemplate = null;
let chatMessages = [];
let personConfig = null;
let chatActive = false;

export async function initCharacterStep(panel) {
  panel.innerHTML = `
    <h2 class="step-section-title" data-i18n="char.title">${t("char.title")}</h2>
    <p class="step-section-desc" data-i18n="char.desc">${t("char.desc")}</p>
    <div id="templateArea">
      <div class="loading-state"><span class="spinner"></span></div>
    </div>
    <div id="chatArea" style="display: none;"></div>
  `;

  await loadTemplates(panel);
}

async function loadTemplates(panel) {
  const area = panel.querySelector("#templateArea");

  try {
    const res = await fetch("/api/setup/templates");
    if (!res.ok) throw new Error("Failed to load templates");
    const data = await res.json();
    // Normalize template data - backend may return strings or objects
    templates = (data.templates || []).map(tmpl => {
      if (typeof tmpl === "string") {
        return { id: tmpl, name: tmpl, description: "", icon: "\u{1F464}" };
      }
      return tmpl;
    });
  } catch {
    templates = [
      { id: "assistant", name: "Assistant", description: "A helpful general assistant", icon: "\u{1F916}" },
      { id: "creative", name: "Creative", description: "A creative and artistic personality", icon: "\u{1F3A8}" },
      { id: "analyst", name: "Analyst", description: "An analytical and detail-oriented mind", icon: "\u{1F4CA}" },
      { id: "custom", name: "Custom", description: "Start from scratch", icon: "\u{2728}" },
    ];
  }

  renderTemplates(panel);
}

function renderTemplates(panel) {
  const area = panel.querySelector("#templateArea");

  let cards = templates.map((tmpl) => `
    <div class="template-card ${selectedTemplate === tmpl.id ? "selected" : ""}" data-template="${tmpl.id}">
      <div class="template-icon">${tmpl.icon || "\u{1F464}"}</div>
      <div class="template-name">${tmpl.name}</div>
      <div class="template-desc">${tmpl.description}</div>
    </div>
  `).join("");

  area.innerHTML = `
    <div class="card-title">${t("char.select_template")}</div>
    <div class="template-grid">${cards}</div>
  `;

  area.querySelectorAll(".template-card").forEach((card) => {
    card.addEventListener("click", () => {
      selectedTemplate = card.dataset.template;
      area.querySelectorAll(".template-card").forEach((c) =>
        c.classList.toggle("selected", c.dataset.template === selectedTemplate)
      );
      showChat(panel);
    });
  });

  // If already selected, show chat
  if (selectedTemplate && chatMessages.length > 0) {
    showChat(panel);
  }
}

function showChat(panel) {
  const chatArea = panel.querySelector("#chatArea");
  chatArea.style.display = "block";

  chatArea.innerHTML = `
    <div class="chat-container">
      <div class="chat-messages" id="setupChatMessages"></div>
      <div class="chat-input-area">
        <textarea class="chat-input" id="setupChatInput"
          placeholder="${t("char.chat.placeholder")}"
          rows="1"></textarea>
        <button class="chat-send-btn" id="setupChatSend">${t("btn.send")}</button>
      </div>
    </div>
    <p class="form-hint" style="margin-top: 8px;">${t("char.chat.hint")}</p>
  `;

  const messagesEl = chatArea.querySelector("#setupChatMessages");
  const inputEl = chatArea.querySelector("#setupChatInput");
  const sendBtn = chatArea.querySelector("#setupChatSend");

  // Render existing messages
  renderChatMessages(messagesEl);

  // Start initial conversation if no messages yet
  if (chatMessages.length === 0) {
    startChat(messagesEl);
  }

  // Wire up send
  sendBtn.addEventListener("click", () => {
    sendMessage(inputEl, messagesEl, sendBtn);
  });

  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(inputEl, messagesEl, sendBtn);
    }
  });

  // Auto-resize textarea
  inputEl.addEventListener("input", () => {
    inputEl.style.height = "auto";
    inputEl.style.height = Math.min(inputEl.scrollHeight, 100) + "px";
  });
}

function renderChatMessages(container) {
  if (chatMessages.length === 0) return;

  container.innerHTML = chatMessages.map((msg) => {
    if (msg.role === "user") {
      return `<div class="chat-bubble user">${escapeHtml(msg.text)}</div>`;
    }
    let content = "";
    try {
      content = marked.parse(msg.text || "", { breaks: true });
    } catch {
      content = escapeHtml(msg.text || "");
    }
    const streamClass = msg.streaming ? " streaming" : "";
    return `<div class="chat-bubble assistant${streamClass}">${content}</div>`;
  }).join("");

  container.scrollTop = container.scrollHeight;
}

async function startChat(container) {
  chatActive = true;
  const streamingMsg = { role: "assistant", text: "", streaming: true };
  chatMessages.push(streamingMsg);

  // Show typing indicator
  container.innerHTML += `<div class="typing-indicator"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div>`;
  container.scrollTop = container.scrollHeight;

  try {
    const res = await fetch("/api/setup/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template: selectedTemplate,
        locale: getLocale(),
        messages: [],
      }),
    });

    if (!res.ok) throw new Error("Chat API error");

    // Remove typing indicator
    const typing = container.querySelector(".typing-indicator");
    if (typing) typing.remove();

    await streamResponse(res, streamingMsg, container);
  } catch (e) {
    const typing = container.querySelector(".typing-indicator");
    if (typing) typing.remove();
    streamingMsg.text = `[Error] ${e.message}`;
    streamingMsg.streaming = false;
    renderChatMessages(container);
  }

  chatActive = false;
}

async function sendMessage(inputEl, container, sendBtn) {
  const text = inputEl.value.trim();
  if (!text || chatActive) return;

  chatActive = true;
  inputEl.value = "";
  inputEl.style.height = "auto";
  inputEl.disabled = true;
  sendBtn.disabled = true;

  // Add user message
  chatMessages.push({ role: "user", text });

  // Add streaming assistant message
  const streamingMsg = { role: "assistant", text: "", streaming: true };
  chatMessages.push(streamingMsg);
  renderChatMessages(container);

  // Show typing indicator
  container.innerHTML += `<div class="typing-indicator"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div>`;
  container.scrollTop = container.scrollHeight;

  try {
    // Build messages for API (exclude streaming)
    const apiMessages = chatMessages
      .filter((m) => !m.streaming)
      .map((m) => ({ role: m.role, content: m.text }));

    const res = await fetch("/api/setup/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template: selectedTemplate,
        locale: getLocale(),
        messages: apiMessages,
      }),
    });

    if (!res.ok) throw new Error("Chat API error");

    const typing = container.querySelector(".typing-indicator");
    if (typing) typing.remove();

    await streamResponse(res, streamingMsg, container);
  } catch (e) {
    const typing = container.querySelector(".typing-indicator");
    if (typing) typing.remove();
    streamingMsg.text = `[Error] ${e.message}`;
    streamingMsg.streaming = false;
    renderChatMessages(container);
  } finally {
    chatActive = false;
    inputEl.disabled = false;
    sendBtn.disabled = false;
    inputEl.focus();
  }
}

async function streamResponse(response, streamingMsg, container) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const { parsed, remaining } = parseSSEEvents(buffer);
    buffer = remaining;

    for (const evt of parsed) {
      switch (evt.event) {
        case "text_delta":
          streamingMsg.text += evt.data.text;
          updateStreamingBubble(container, streamingMsg);
          break;

        case "done":
          if (evt.data.person_config) {
            personConfig = evt.data.person_config;
          }
          streamingMsg.text = evt.data.summary || streamingMsg.text || "(empty)";
          streamingMsg.streaming = false;
          renderChatMessages(container);
          break;

        case "error":
          streamingMsg.text += `\n[Error] ${evt.data.message}`;
          streamingMsg.streaming = false;
          renderChatMessages(container);
          break;
      }
    }
  }

  // Ensure finalized
  if (streamingMsg.streaming) {
    streamingMsg.streaming = false;
    if (!streamingMsg.text) streamingMsg.text = "(empty)";
    renderChatMessages(container);
  }
}

function updateStreamingBubble(container, msg) {
  const bubbles = container.querySelectorAll(".chat-bubble.assistant.streaming");
  const bubble = bubbles[bubbles.length - 1];
  if (!bubble) {
    renderChatMessages(container);
    return;
  }

  let html = "";
  try {
    html = marked.parse(msg.text, { breaks: true });
  } catch {
    html = escapeHtml(msg.text);
  }
  if (!html) {
    html = '<span class="cursor-blink"></span>';
  }

  bubble.innerHTML = html;
  container.scrollTop = container.scrollHeight;
}

function parseSSEEvents(buffer) {
  const parsed = [];
  const parts = buffer.split("\n\n");
  const remaining = parts.pop() || "";

  for (const part of parts) {
    if (!part.trim()) continue;
    let eventName = "message";
    let dataLines = [];
    for (const line of part.split("\n")) {
      if (line.startsWith("event: ")) {
        eventName = line.slice(7);
      } else if (line.startsWith("data: ")) {
        dataLines.push(line.slice(6));
      }
    }
    if (dataLines.length > 0) {
      try {
        parsed.push({ event: eventName, data: JSON.parse(dataLines.join("\n")) });
      } catch (e) {
        console.warn("SSE parse error:", e);
      }
    }
  }

  return { parsed, remaining };
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

export function validateCharacter() {
  return selectedTemplate !== null;
}

export function getCharacterData() {
  return {
    template: selectedTemplate,
    person_config: personConfig,
    chat_history: chatMessages
      .filter((m) => !m.streaming)
      .map((m) => ({ role: m.role, content: m.text })),
  };
}
