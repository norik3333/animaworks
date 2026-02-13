// ── Person Selector & Status Panel ──────────────────────
// Dropdown for person selection + detail card rendering.

import { getState, setState } from "./state.js";
import { fetchPersons, fetchPersonDetail } from "./api.js";
import { escapeHtml } from "./utils.js";

// ── Private State ──────────────────────

let _selectorContainer = null;
let _statusContainer = null;
let _onPersonSelect = null;

// ── Helpers ──────────────────────

/**
 * Map a status string to its CSS class.
 */
function statusClassName(status) {
  if (!status) return "status-offline";
  const s = status.toLowerCase();
  if (s === "idle" || s === "running") return "status-idle";
  if (s === "thinking" || s === "processing" || s === "busy") return "status-thinking";
  if (s === "error") return "status-error";
  return "status-offline";
}

/**
 * Map a status string to a display label.
 */
function statusLabel(status) {
  if (!status) return "offline";
  return status.toLowerCase();
}

// ── Dropdown Rendering ──────────────────────

function renderDropdown() {
  if (!_selectorContainer) return;

  const { persons, selectedPerson } = getState();

  let html = '<select class="person-dropdown" id="wsPersonDropdown">';
  html += '<option value="" disabled>Select a person...</option>';

  for (const p of persons) {
    const st = p.status ? ` (${p.status})` : "";
    const selected = p.name === selectedPerson ? " selected" : "";
    html += `<option value="${escapeHtml(p.name)}"${selected}>${escapeHtml(p.name)}${st}</option>`;
  }

  html += "</select>";
  _selectorContainer.innerHTML = html;

  // Bind change event
  const dropdown = _selectorContainer.querySelector("#wsPersonDropdown");
  if (dropdown) {
    dropdown.addEventListener("change", (e) => {
      const name = e.target.value;
      if (name) selectPerson(name);
    });
  }
}

// ── Status Panel Rendering ──────────────────────

function renderStatusPanel() {
  if (!_statusContainer) return;

  const { personDetail, selectedPerson } = getState();

  if (!selectedPerson) {
    _statusContainer.innerHTML = `
      <div class="person-status-panel">
        <div class="loading-placeholder">Select a person to view details</div>
      </div>
    `;
    return;
  }

  if (!personDetail) {
    _statusContainer.innerHTML = `
      <div class="person-status-panel">
        <div class="loading-placeholder">Loading...</div>
      </div>
    `;
    return;
  }

  const d = personDetail;
  const rawStatus = d.status;
  const statusStr = (rawStatus && typeof rawStatus === "object") ? (rawStatus.status || "offline") : (rawStatus || "offline");
  const dotClass = statusClassName(statusStr);

  // Build sections
  let sectionsHtml = "";

  // Identity section
  if (d.identity) {
    sectionsHtml += `
      <div class="status-section">
        <div class="status-section-title">Identity</div>
        <div class="status-section-body">${escapeHtml(truncate(d.identity, 500))}</div>
      </div>
    `;
  }

  // Injection section
  if (d.injection) {
    sectionsHtml += `
      <div class="status-section">
        <div class="status-section-title">Injection</div>
        <div class="status-section-body">${escapeHtml(truncate(d.injection, 500))}</div>
      </div>
    `;
  }

  // State section
  if (d.state) {
    const stateText = typeof d.state === "string" ? d.state : JSON.stringify(d.state, null, 2);
    sectionsHtml += `
      <div class="status-section">
        <div class="status-section-title">State</div>
        <div class="status-section-body"><pre>${escapeHtml(stateText)}</pre></div>
      </div>
    `;
  }

  // Pending section
  if (d.pending) {
    const pendingText =
      typeof d.pending === "string" ? d.pending : JSON.stringify(d.pending, null, 2);
    sectionsHtml += `
      <div class="status-section">
        <div class="status-section-title">Pending</div>
        <div class="status-section-body"><pre>${escapeHtml(pendingText)}</pre></div>
      </div>
    `;
  }

  // Fallback if no sections
  if (!sectionsHtml) {
    sectionsHtml = '<div class="loading-placeholder">No detail available</div>';
  }

  _statusContainer.innerHTML = `
    <div class="person-status-panel">
      <div class="status-header">
        <span class="status-dot ${dotClass}"></span>
        <span class="status-person-name">${escapeHtml(selectedPerson)}</span>
        <span class="status-label">${escapeHtml(statusLabel(statusStr))}</span>
      </div>
      ${sectionsHtml}
    </div>
  `;
}

function truncate(str, maxLen) {
  if (!str) return "";
  if (str.length <= maxLen) return str;
  return str.slice(0, maxLen) + "...";
}

// ── Public API ──────────────────────

/**
 * Render the person selector dropdown into the given container.
 */
export function renderPersonSelector(container) {
  _selectorContainer = container || _selectorContainer;
  renderDropdown();
}

/**
 * Render the person status detail panel into the given container.
 */
export function renderStatus(container) {
  _statusContainer = container || _statusContainer;
  renderStatusPanel();
}

/**
 * Initialize the person module.
 * @param {HTMLElement} selectorContainer - DOM element for the dropdown
 * @param {HTMLElement} statusContainer - DOM element for the status panel
 * @param {function} onPersonSelect - Callback invoked with person name on selection
 */
export function initPerson(selectorContainer, statusContainer, onPersonSelect) {
  _selectorContainer = selectorContainer;
  _statusContainer = statusContainer;
  _onPersonSelect = onPersonSelect;

  // Render initial empty state
  renderDropdown();
  renderStatusPanel();
}

/**
 * Load persons list from API and update the dropdown.
 */
export async function loadPersons() {
  try {
    const persons = await fetchPersons();
    setState({ persons });
    renderDropdown();

    // Auto-select first person if none selected
    const { selectedPerson } = getState();
    if (persons.length > 0 && !selectedPerson) {
      await selectPerson(persons[0].name);
    }
  } catch (err) {
    console.error("Failed to load persons:", err);
    if (_selectorContainer) {
      _selectorContainer.innerHTML =
        '<div class="loading-placeholder" style="color:#ef4444;">Failed to load persons</div>';
    }
  }
}

/**
 * Select a person by name. Fetches detail and updates state + UI.
 */
export async function selectPerson(name) {
  setState({ selectedPerson: name, personDetail: null });
  renderDropdown();
  renderStatusPanel();

  try {
    const detail = await fetchPersonDetail(name);
    setState({ personDetail: detail });
    renderStatusPanel();
  } catch (err) {
    console.error(`Failed to load person detail for "${name}":`, err);
    if (_statusContainer) {
      _statusContainer.innerHTML = `
        <div class="person-status-panel">
          <div class="loading-placeholder" style="color:#ef4444;">
            Failed to load details for ${escapeHtml(name)}
          </div>
        </div>
      `;
    }
  }

  // Notify callback
  if (_onPersonSelect) {
    _onPersonSelect(name);
  }
}
