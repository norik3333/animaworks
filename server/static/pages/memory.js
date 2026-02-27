// ── Memory Browser (Full Page) ──────────────
import { api } from "../modules/api.js";
import { escapeHtml, renderMarkdown } from "../modules/state.js";
import { t } from "/shared/i18n.js";

let _selectedAnima = null;
let _activeTab = "episodes";
let _viewMode = "list"; // "list" | "content"
let _container = null;
let _animas = [];
const _TAB_META = {
  episodes: { icon: "📝", labelKey: "chat.memory_episodes" },
  knowledge: { icon: "📘", labelKey: "chat.memory_knowledge" },
  procedures: { icon: "📑", labelKey: "chat.memory_procedures" },
};

function _extractStatsCount(value) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (value && typeof value === "object") {
    const count = value.count;
    if (typeof count === "number" && Number.isFinite(count)) return count;
  }
  return 0;
}

function _tabLabel(tab, count = null) {
  const meta = _TAB_META[tab];
  if (!meta) return "";
  const base = `${meta.icon} ${t(meta.labelKey)}`;
  return count === null ? base : `${base} (${count})`;
}

function _setTabLabel(tab, count = null) {
  const btn = _container?.querySelector(`.page-tab[data-tab="${tab}"]`);
  if (!btn) return;
  btn.textContent = _tabLabel(tab, count);
}

function _resetTabLabels() {
  _setTabLabel("episodes", null);
  _setTabLabel("knowledge", null);
  _setTabLabel("procedures", null);
}

export function render(container) {
  _container = container;
  _selectedAnima = null;
  _activeTab = "episodes";
  _viewMode = "list";

  container.innerHTML = `
    <div class="page-header">
      <h2>${t("memory.page_title")}</h2>
    </div>

    <div style="display:flex; gap:1rem; align-items:center; margin-bottom:1rem;">
      <label style="font-weight:500;">Anima:</label>
      <select id="memoryAnimaSelect" class="anima-dropdown" style="flex:1; max-width:300px;">
        <option value="">${t("memory.select_anima")}</option>
      </select>
    </div>

    <div class="page-tabs" style="margin-bottom:1rem;">
      <button class="page-tab active" data-tab="episodes">${_tabLabel("episodes")}</button>
      <button class="page-tab" data-tab="knowledge">${_tabLabel("knowledge")}</button>
      <button class="page-tab" data-tab="procedures">${_tabLabel("procedures")}</button>
    </div>

    <div class="card">
      <div class="card-body" id="memoryMainContent">
        <div class="loading-placeholder">${t("assets.select_anima")}</div>
      </div>
    </div>
  `;

  _loadAnimaList();
  _bindEvents();
  _resetTabLabels();
}

export function destroy() {
  _container = null;
  _animas = [];
}

// ── Event Binding ──────────────────────────

function _bindEvents() {
  if (!_container) return;

  // Anima selector
  const select = document.getElementById("memoryAnimaSelect");
  if (select) {
    select.addEventListener("change", (e) => {
      _selectedAnima = e.target.value || null;
      _viewMode = "list";
      _updateTabCounts();
      _loadFileList();
    });
  }

  // Tab buttons
  _container.querySelectorAll(".page-tab").forEach(btn => {
    btn.addEventListener("click", () => {
      _activeTab = btn.dataset.tab;
      _container.querySelectorAll(".page-tab").forEach(b => b.classList.toggle("active", b.dataset.tab === _activeTab));
      _viewMode = "list";
      _loadFileList();
    });
  });
}

// ── Data Loading ───────────────────────────

async function _loadAnimaList() {
  const select = document.getElementById("memoryAnimaSelect");
  if (!select) return;

  try {
    _animas = await api("/api/animas");
    let opts = `<option value="">${t("memory.select_anima")}</option>`;
    for (const p of _animas) {
      opts += `<option value="${escapeHtml(p.name)}">${escapeHtml(p.name)}</option>`;
    }
    select.innerHTML = opts;
  } catch {
    select.innerHTML = `<option value="">${t("memory.fetch_failed")}</option>`;
  }
}

async function _updateTabCounts() {
  if (!_selectedAnima) {
    _resetTabLabels();
    return;
  }

  let epCount = 0, knCount = 0, prCount = 0;

  // Try memory stats endpoint first
  try {
    const stats = await api(`/api/animas/${encodeURIComponent(_selectedAnima)}/memory/stats`);
    epCount = _extractStatsCount(stats.episodes);
    knCount = _extractStatsCount(stats.knowledge);
    prCount = _extractStatsCount(stats.procedures);
  } catch {
    // Fallback: count from file list endpoints
    try {
      const [ep, kn, pr] = await Promise.all([
        api(`/api/animas/${encodeURIComponent(_selectedAnima)}/episodes`).catch(() => ({ files: [] })),
        api(`/api/animas/${encodeURIComponent(_selectedAnima)}/knowledge`).catch(() => ({ files: [] })),
        api(`/api/animas/${encodeURIComponent(_selectedAnima)}/procedures`).catch(() => ({ files: [] })),
      ]);
      epCount = (ep.files || []).length;
      knCount = (kn.files || []).length;
      prCount = (pr.files || []).length;
    } catch { /* ignore */ }
  }
  _setTabLabel("episodes", epCount);
  _setTabLabel("knowledge", knCount);
  _setTabLabel("procedures", prCount);
}

async function _loadFileList() {
  const content = document.getElementById("memoryMainContent");
  if (!content) return;

  if (!_selectedAnima) {
    content.innerHTML = `<div class="loading-placeholder">${t("assets.select_anima")}</div>`;
    return;
  }

  content.innerHTML = `<div class="loading-placeholder">${t("common.loading")}</div>`;

  const endpoint = `/api/animas/${encodeURIComponent(_selectedAnima)}/${_activeTab}`;

  try {
    const data = await api(endpoint);
    const files = data.files || [];

    if (files.length === 0) {
      content.innerHTML = `<div class="loading-placeholder">${t("memory.no_files")}</div>`;
      return;
    }

    content.innerHTML = files.map(f =>
      `<div class="memory-file-item" data-file="${escapeHtml(f)}" style="padding:0.5rem 0.75rem; border-bottom:1px solid var(--border-color, #eee); cursor:pointer;">
        ${escapeHtml(f)}
      </div>`
    ).join("");

    content.querySelectorAll(".memory-file-item").forEach(item => {
      item.addEventListener("click", () => {
        _loadFileContent(item.dataset.file);
      });
      item.addEventListener("mouseenter", () => { item.style.background = "var(--hover-bg, #f5f5f5)"; });
      item.addEventListener("mouseleave", () => { item.style.background = ""; });
    });
  } catch (err) {
    content.innerHTML = `<div class="loading-placeholder">${t("memory.fetch_failed")}: ${escapeHtml(err.message)}</div>`;
  }
}

async function _loadFileContent(file) {
  const content = document.getElementById("memoryMainContent");
  if (!content || !_selectedAnima) return;

  _viewMode = "content";

  content.innerHTML = `
    <div>
      <button class="btn-secondary" id="memoryBackToList" style="margin-bottom:1rem;">&larr; ${t("animas.back")}</button>
      <h3 style="margin-bottom:0.75rem;">${escapeHtml(file)}</h3>
      <div id="memoryFileBody" class="loading-placeholder">${t("common.loading")}</div>
    </div>
  `;

  document.getElementById("memoryBackToList")?.addEventListener("click", () => {
    _viewMode = "list";
    _loadFileList();
  });

  const endpoint = `/api/animas/${encodeURIComponent(_selectedAnima)}/${_activeTab}/${encodeURIComponent(file)}`;

  try {
    const data = await api(endpoint);
    const body = document.getElementById("memoryFileBody");
    if (body) {
      const raw = data.content || t("chat.no_content");
      body.className = "";
      body.innerHTML = `<div style="background:var(--bg-secondary, #f8f9fa); padding:1rem; border-radius:0.5rem;">${renderMarkdown(raw)}</div>`;
    }
  } catch (err) {
    const body = document.getElementById("memoryFileBody");
    if (body) {
      body.className = "loading-placeholder";
      body.textContent = `${t("memory.fetch_failed")}: ${err.message}`;
    }
  }
}
