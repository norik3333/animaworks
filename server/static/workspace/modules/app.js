// ── App Entry Point ──────────────────────
// Initialization, screen switching, and event delegation.

import { getState, setState, subscribe } from "./state.js";
import { fetchSystemStatus } from "./api.js";
import { connect, onEvent } from "./websocket.js";
import { initLogin, getCurrentUser, logout } from "./login.js";
import { initPerson, loadPersons, selectPerson, renderPersonSelector, renderStatus } from "./person.js";
import { renderChat, initChat, sendMessage, addMessage, loadConversation } from "./chat.js";
import { initMemory, loadMemoryTab } from "./memory.js";
import { initSession, loadSessions } from "./session.js";
import { escapeHtml } from "./utils.js";

// ── DOM References ──────────────────────

const dom = {};

function cacheDom() {
  dom.loginContainer = document.getElementById("wsLogin");
  dom.dashboard = document.getElementById("wsDashboard");
  dom.personSelector = document.getElementById("wsPersonSelector");
  dom.systemStatus = document.getElementById("wsSystemStatus");
  dom.userInfo = document.getElementById("wsUserInfo");
  dom.chatPanel = document.getElementById("wsChatPanel");
  dom.rightTabs = document.getElementById("wsRightTabs");
  dom.tabState = document.getElementById("wsTabState");
  dom.tabActivity = document.getElementById("wsTabActivity");
  dom.tabHistory = document.getElementById("wsTabHistory");
  dom.paneState = document.getElementById("wsPaneState");
  dom.paneActivity = document.getElementById("wsPaneActivity");
  dom.paneHistory = document.getElementById("wsPaneHistory");
  dom.memoryPanel = document.getElementById("wsMemoryPanel");
  dom.logoutBtn = document.getElementById("wsLogoutBtn");
}

// ── Activity Feed ──────────────────────

const TYPE_ICONS = {
  heartbeat: "\uD83D\uDC93",
  cron: "\u23F0",
  chat: "\uD83D\uDCAC",
  system: "\u2699\uFE0F",
};

function addActivity(type, personName, summary) {
  if (!dom.paneActivity) return;

  const now = new Date();
  const ts = now.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit" });
  const icon = TYPE_ICONS[type] || "\u2022";

  const entry = document.createElement("div");
  entry.className = "activity-entry";
  entry.innerHTML = `
    <span class="activity-time">${ts}</span>
    <span class="activity-icon">${icon}</span>
    <span class="activity-person">${escapeHtml(personName)}</span>
    <span class="activity-summary">${escapeHtml(summary)}</span>`;

  dom.paneActivity.prepend(entry);

  // Cap at 200 entries
  while (dom.paneActivity.children.length > 200) {
    dom.paneActivity.removeChild(dom.paneActivity.lastChild);
  }
}

// ── Right Panel Tabs ──────────────────────

function activateRightTab(tab) {
  setState({ activeRightTab: tab });

  [dom.tabState, dom.tabActivity, dom.tabHistory].forEach((btn) => {
    btn?.classList.toggle("active", btn.dataset.tab === tab);
  });

  [dom.paneState, dom.paneActivity, dom.paneHistory].forEach((pane) => {
    if (pane) pane.style.display = pane.dataset.pane === tab ? "" : "none";
  });

  if (tab === "history") {
    loadSessions();
  }
}

// ── System Status ──────────────────────

async function loadSystemStatus() {
  if (!dom.systemStatus) return;
  try {
    const data = await fetchSystemStatus();
    updateStatusDisplay(
      data.scheduler_running,
      `${data.scheduler_running ? "稼働中" : "停止"} (${data.persons}名)`
    );
  } catch {
    updateStatusDisplay(false, "接続失敗");
  }
}

function updateStatusDisplay(ok, text) {
  if (!dom.systemStatus) return;
  const dot = dom.systemStatus.querySelector(".status-dot");
  const label = dom.systemStatus.querySelector(".status-text");
  if (dot) dot.className = `status-dot ${ok ? "status-idle" : "status-error"}`;
  if (label) label.textContent = text;
}

// ── WebSocket Handlers ──────────────────────

const wsUnsubscribers = [];

function setupWebSocket() {
  // Clean up previous handlers
  wsUnsubscribers.forEach((fn) => fn());
  wsUnsubscribers.length = 0;

  connect();

  wsUnsubscribers.push(onEvent("person.status", (data) => {
    const { persons, selectedPerson } = getState();
    const idx = persons.findIndex((p) => p.name === data.name);
    if (idx >= 0) {
      persons[idx] = { ...persons[idx], ...data };
      setState({ persons: [...persons] });
      renderPersonSelector(dom.personSelector);
    }
    if (data.name === selectedPerson) {
      renderStatus(dom.paneState);
    }
    addActivity("system", data.name, `Status: ${data.status}`);
  }));

  wsUnsubscribers.push(onEvent("person.heartbeat", (data) => {
    addActivity("heartbeat", data.name, data.summary || "heartbeat completed");
    const { selectedPerson } = getState();
    if (data.name === selectedPerson) {
      renderStatus(dom.paneState);
    }
  }));

  wsUnsubscribers.push(onEvent("person.cron", (data) => {
    addActivity("cron", data.name, data.summary || `cron: ${data.job || ""}`);
  }));

  wsUnsubscribers.push(onEvent("chat.response", (data) => {
    const personName = data.person || data.name;
    const msg = data.response || data.message || "";
    const { selectedPerson } = getState();
    if (personName === selectedPerson) {
      addMessage("assistant", msg);
    }
    addActivity("chat", personName, msg.slice(0, 60));
  }));

  // Track connection state for status indicator
  wsUnsubscribers.push(subscribe((state) => {
    if (state.wsConnected) {
      updateStatusDisplay(true, `接続済 (${state.persons.length}名)`);
    } else {
      updateStatusDisplay(false, "再接続中...");
    }
  }));
}

// ── Dashboard Bootstrap ──────────────────────

let dashboardInitialized = false;

async function startDashboard() {
  if (!dom.dashboard) return;

  // Show dashboard, update user info
  dom.dashboard.classList.remove("hidden");
  if (dom.userInfo) {
    dom.userInfo.textContent = getCurrentUser() || "";
  }

  if (dashboardInitialized) {
    // Re-login: just refresh data
    await loadPersons();
    await loadSystemStatus();
    return;
  }
  dashboardInitialized = true;

  // Initialize sub-modules
  initPerson(dom.personSelector, dom.paneState, onPersonSelected);
  renderChat(dom.chatPanel);
  initChat(dom.chatPanel);
  initMemory(dom.memoryPanel);
  initSession(dom.paneHistory);

  // Bind right-panel tabs
  [dom.tabState, dom.tabActivity, dom.tabHistory].forEach((btn) => {
    btn?.addEventListener("click", () => activateRightTab(btn.dataset.tab));
  });

  // Bind logout
  dom.logoutBtn?.addEventListener("click", () => {
    dom.dashboard.classList.add("hidden");
    logout();
  });

  // Load data
  await loadPersons();
  await loadSystemStatus();

  // Connect WebSocket
  setupWebSocket();

  // Activate default right tab
  activateRightTab("state");
}

// ── Person Selection Callback ──────────────────────

async function onPersonSelected(name) {
  // Load conversation + memory + sessions in parallel
  await Promise.all([
    loadConversation(),
    loadMemoryTab(getState().activeMemoryTab),
    loadSessions(),
  ]);
}

// ── Main Init ──────────────────────

export function init() {
  cacheDom();

  const savedUser = getCurrentUser();
  if (savedUser) {
    // Already logged in — render login (hidden) and go to dashboard
    initLogin(dom.loginContainer, onLoginSuccess);
    startDashboard();
  } else {
    // Show login screen
    dom.dashboard?.classList.add("hidden");
    initLogin(dom.loginContainer, onLoginSuccess);
  }
}

function onLoginSuccess(_username) {
  startDashboard();
}

// Auto-init on DOM ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
