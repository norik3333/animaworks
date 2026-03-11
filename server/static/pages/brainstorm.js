/* ── AI Brainstorm Page ──────────────────────── */

import { api } from "../modules/api.js";
import { renderMarkdown, escapeHtml } from "../modules/state.js";
import { t } from "/shared/i18n.js";

let _abortCtrl = null;

const CHAR_ICONS = {
  realist: "chart-line",
  challenger: "rocket",
  customer: "heart",
  engineer: "wrench",
};

export async function render(container) {
  container.innerHTML = `
    <div class="brainstorm-page">
      <div class="page-header">
        <h2>${t("brainstorm.page_title")}</h2>
        <p class="page-desc">${t("brainstorm.page_desc")}</p>
      </div>

      <div class="brainstorm-input card">
        <div class="card-header">${t("brainstorm.input_title")}</div>
        <div class="card-body">
          <div class="bs-field">
            <label for="bsTheme">${t("brainstorm.theme_label")}</label>
            <textarea id="bsTheme" class="bs-textarea" rows="3"
              placeholder="${escapeHtml(t("brainstorm.theme_placeholder"))}"></textarea>
          </div>
          <div class="bs-field">
            <label for="bsConstraints">${t("brainstorm.constraints_label")}</label>
            <textarea id="bsConstraints" class="bs-textarea" rows="2"
              placeholder="${escapeHtml(t("brainstorm.constraints_placeholder"))}"></textarea>
          </div>
          <div class="bs-field">
            <label for="bsExpected">${t("brainstorm.expected_label")}</label>
            <textarea id="bsExpected" class="bs-textarea" rows="2"
              placeholder="${escapeHtml(t("brainstorm.expected_placeholder"))}"></textarea>
          </div>
        </div>
      </div>

      <div class="brainstorm-chars card">
        <div class="card-header">${t("brainstorm.chars_title")}</div>
        <div class="card-body">
          <div id="bsCharList" class="bs-char-list"></div>
        </div>
      </div>

      <div class="brainstorm-controls card">
        <div class="card-body bs-controls-inner">
          <div class="bs-control-row">
            <label for="bsModel">${t("brainstorm.model_label")}</label>
            <select id="bsModel" class="bs-model-select">
              <option value="">${t("brainstorm.model_default")}</option>
            </select>
          </div>
          <div class="bs-btn-row">
            <button id="bsGenBtn" class="btn btn-primary">${t("brainstorm.generate_btn")}</button>
          </div>
        </div>
      </div>

      <div id="bsStatus" class="bs-status" style="display:none"></div>

      <div id="bsResults" style="display:none">
        <div id="bsProposals" class="bs-proposals"></div>
        <div id="bsSynthesis" class="bs-synthesis card" style="display:none">
          <div class="card-header">${t("brainstorm.synthesis_title")}</div>
          <div class="card-body markdown-body" id="bsSynthContent"></div>
        </div>
      </div>
    </div>
  `;

  _loadCharacters(container);
  _loadModels(container);

  container.querySelector("#bsGenBtn").addEventListener("click", () => _onGenerate(container));
}

export function destroy() {
  if (_abortCtrl) {
    _abortCtrl.abort();
    _abortCtrl = null;
  }
}

// ── Character list ──────────────────────────

async function _loadCharacters(container) {
  try {
    const data = await api("/api/brainstorm/characters");
    const list = container.querySelector("#bsCharList");
    if (!list || !data.characters) return;

    list.innerHTML = data.characters
      .map(
        (c) => `
      <label class="bs-char-item" data-char-id="${escapeHtml(c.id)}">
        <input type="checkbox" value="${escapeHtml(c.id)}" checked />
        <i data-lucide="${escapeHtml(c.icon)}" class="bs-char-icon"></i>
        <div class="bs-char-info">
          <span class="bs-char-name">${escapeHtml(c.name)}</span>
          <span class="bs-char-desc">${escapeHtml(c.description)}</span>
        </div>
      </label>
    `
      )
      .join("");

    // Re-render lucide icons if available
    if (window.lucide) window.lucide.createIcons();
  } catch (e) {
    console.error("Failed to load characters:", e);
  }
}

// ── Model dropdown ──────────────────────────

async function _loadModels(container) {
  try {
    const data = await api("/api/brainstorm/models");
    const sel = container.querySelector("#bsModel");
    if (!sel || !data.available_models) return;

    for (const m of data.available_models) {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = m.label;
      if (m.id === data.default_model) opt.selected = true;
      sel.appendChild(opt);
    }
  } catch (e) {
    console.error("Failed to load models:", e);
  }
}

// ── Generate ────────────────────────────────

async function _onGenerate(container) {
  const theme = container.querySelector("#bsTheme")?.value?.trim();
  if (!theme) {
    _showStatus(container, t("brainstorm.theme_required"), "error");
    return;
  }

  const constraints = container.querySelector("#bsConstraints")?.value?.trim() || "";
  const expected = container.querySelector("#bsExpected")?.value?.trim() || "";
  const model = container.querySelector("#bsModel")?.value || "";

  const checked = container.querySelectorAll("#bsCharList input[type=checkbox]:checked");
  const charIds = Array.from(checked).map((el) => el.value);
  if (charIds.length === 0) {
    _showStatus(container, t("brainstorm.no_chars_error"), "error");
    return;
  }

  const btn = container.querySelector("#bsGenBtn");
  btn.disabled = true;
  btn.textContent = t("brainstorm.generating");

  _showStatus(container, t("brainstorm.generating_msg"), "loading");
  container.querySelector("#bsResults").style.display = "none";

  if (_abortCtrl) _abortCtrl.abort();
  _abortCtrl = new AbortController();

  try {
    const data = await api("/api/brainstorm/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        theme,
        constraints,
        expected_output: expected,
        character_ids: charIds,
        model,
      }),
      signal: _abortCtrl.signal,
    });

    _renderResults(container, data);
    _showStatus(container, "", "hide");
  } catch (e) {
    if (e.name !== "AbortError") {
      _showStatus(container, t("brainstorm.generate_error") + ": " + e.message, "error");
    }
  } finally {
    btn.disabled = false;
    btn.textContent = t("brainstorm.generate_btn");
    _abortCtrl = null;
  }
}

// ── Render results ──────────────────────────

function _renderResults(container, data) {
  const resultsEl = container.querySelector("#bsResults");
  const proposalsEl = container.querySelector("#bsProposals");
  const synthEl = container.querySelector("#bsSynthesis");
  const synthContent = container.querySelector("#bsSynthContent");

  resultsEl.style.display = "block";

  // Render individual proposals
  proposalsEl.innerHTML = data.proposals
    .map((p) => {
      const icon = CHAR_ICONS[p.character_id] || "message-circle";
      if (p.error) {
        return `
          <div class="bs-proposal card">
            <div class="card-header bs-proposal-header">
              <i data-lucide="${escapeHtml(icon)}" class="bs-char-icon"></i>
              ${escapeHtml(p.character_name)}
            </div>
            <div class="card-body bs-proposal-error">${escapeHtml(p.error)}</div>
          </div>
        `;
      }
      return `
        <div class="bs-proposal card">
          <div class="card-header bs-proposal-header" data-action="toggle">
            <i data-lucide="${escapeHtml(icon)}" class="bs-char-icon"></i>
            ${escapeHtml(p.character_name)}
            <i data-lucide="chevron-down" class="bs-toggle-icon"></i>
          </div>
          <div class="card-body markdown-body bs-proposal-body">${renderMarkdown(p.proposal || "")}</div>
        </div>
      `;
    })
    .join("");

  // Collapse/expand individual proposals
  proposalsEl.querySelectorAll("[data-action=toggle]").forEach((header) => {
    header.addEventListener("click", () => {
      const body = header.nextElementSibling;
      const icon = header.querySelector(".bs-toggle-icon");
      if (body.style.display === "none") {
        body.style.display = "";
        icon?.setAttribute("data-lucide", "chevron-down");
      } else {
        body.style.display = "none";
        icon?.setAttribute("data-lucide", "chevron-right");
      }
      if (window.lucide) window.lucide.createIcons();
    });
  });

  // Render synthesis
  if (data.synthesis) {
    synthEl.style.display = "block";
    synthContent.innerHTML = renderMarkdown(data.synthesis);
  } else {
    synthEl.style.display = "none";
  }

  if (window.lucide) window.lucide.createIcons();
}

// ── Status display ──────────────────────────

function _showStatus(container, msg, type) {
  const el = container.querySelector("#bsStatus");
  if (!el) return;

  if (type === "hide") {
    el.style.display = "none";
    return;
  }

  el.style.display = "block";
  el.className = "bs-status bs-status-" + type;

  if (type === "loading") {
    el.innerHTML = `<span class="bs-spinner"></span> ${escapeHtml(msg)}`;
  } else {
    el.textContent = msg;
  }
}
