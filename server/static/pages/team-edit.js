/* ── Team Edit — Screen 5 ─────────────────── */

import { t, applyTranslations } from "/shared/i18n.js";
import { navigateTo } from "../modules/router.js";
import {
  ROLES,
  getTeam,
  getRoleById,
  getRoleName,
  getToolLabel,
  getAllTools,
  addMember,
  removeMember,
  updateMemberRole,
  toggleMemberTool,
} from "../modules/team-data.js";

let _container = null;

// Avatar colors
const AVATAR_COLORS = [
  "#6366f1", "#ec4899", "#f59e0b", "#10b981",
  "#3b82f6", "#8b5cf6", "#ef4444", "#14b8a6",
  "#f97316", "#06b6d4",
];

const ROLE_ICONS = {
  secretary: "\u{1F4CB}",
  customer_support: "\u{1F3E7}",
  back_office: "\u{1F4C1}",
  sales_assist: "\u{1F4C8}",
  pr_sns: "\u{1F4E3}",
  recruiter: "\u{1F465}",
  accounting: "\u{1F4B0}",
  project_manager: "\u{1F3AF}",
  researcher: "\u{1F50D}",
  content_writer: "\u{270D}\uFE0F",
};

// ── Render / Destroy ──────────────────────

export function render(container) {
  _container = container;
  _renderEdit();
}

export function destroy() {
  _container = null;
}

// ── Main Render ───────────────────────────

function _renderEdit() {
  if (!_container) return;

  const team = getTeam();
  if (!team || !team.members || team.members.length === 0) {
    _renderEmpty();
    return;
  }

  const allTools = getAllTools();

  const memberCards = team.members.map((m, idx) => {
    const role = getRoleById(m.roleId);
    const color = AVATAR_COLORS[idx % AVATAR_COLORS.length];
    const initial = m.displayName.charAt(0);
    const icon = ROLE_ICONS[m.roleId] || "\u{1F464}";

    // Role selector options
    const roleOptions = ROLES.map((r) => {
      const selected = r.id === m.roleId ? "selected" : "";
      return `<option value="${r.id}" ${selected}>${t(r.nameKey)}</option>`;
    }).join("");

    // Tool toggles
    const toolChips = allTools.map((tool) => {
      const active = m.tools.includes(tool.id);
      const cls = active ? "tb-tool-toggle active" : "tb-tool-toggle";
      const indicator = active ? "\u2713" : "\u2717";
      return `<button class="${cls}" data-member-id="${m.id}" data-tool-id="${tool.id}">${indicator} ${tool.label}</button>`;
    }).join("");

    return `
      <div class="tb-member-card" data-member="${m.id}">
        <div class="tb-member-avatar" style="background:${color}">${initial}</div>
        <div class="tb-member-info">
          <div class="tb-member-name">${icon} ${m.displayName}</div>
          <div style="display:flex;align-items:center;gap:8px;margin:6px 0;">
            <label style="font-size:0.78rem;color:var(--aw-color-text-muted);flex-shrink:0;">${t("tb.edit.role")}:</label>
            <select class="tb-role-select" data-member-id="${m.id}">
              ${roleOptions}
            </select>
          </div>
          <div style="display:flex;gap:4px;flex-wrap:wrap;">
            ${toolChips}
          </div>
        </div>
        <div class="tb-member-actions">
          <button class="tb-btn-icon danger" data-delete="${m.id}" title="${t("tb.edit.delete")}">\u2715</button>
        </div>
      </div>
    `;
  }).join("");

  _container.innerHTML = `
    <div class="page-header">
      <h2>${t("tb.edit.title")}</h2>
      <p>${t("tb.edit.desc")}</p>
    </div>
    <div class="tb-wizard">
      <div class="tb-member-list">
        ${memberCards}
      </div>
      <button class="tb-add-member-btn" data-action="add">+ ${t("tb.edit.add")}</button>
      <div class="tb-wizard-nav" style="margin-top:16px;">
        <button class="btn-secondary" data-action="back">${t("tb.back")}</button>
        <button class="btn-primary" data-action="chat">${t("tb.step4.chat")}</button>
      </div>
    </div>
  `;

  _bindEditEvents();
  applyTranslations();
}

function _renderEmpty() {
  _container.innerHTML = `
    <div class="page-header">
      <h2>${t("tb.edit.title")}</h2>
    </div>
    <div class="tb-wizard">
      <div style="text-align:center;padding:3rem 1rem;color:var(--aw-color-text-muted);">
        ${t("tb.edit.empty")}
      </div>
      <div class="tb-wizard-nav" style="justify-content:center;">
        <button class="btn-primary" data-action="build">${t("tb.edit.build")}</button>
      </div>
    </div>
  `;

  _container.querySelector("[data-action='build']")?.addEventListener("click", () => {
    navigateTo("#/team-builder");
  });
  applyTranslations();
}

// ── Event Bindings ────────────────────────

function _bindEditEvents() {
  if (!_container) return;

  // Role change
  _container.querySelectorAll(".tb-role-select").forEach((sel) => {
    sel.addEventListener("change", (e) => {
      const memberId = sel.dataset.memberId;
      const newRole = e.target.value;
      updateMemberRole(memberId, newRole);
      _renderEdit();
    });
  });

  // Tool toggle
  _container.querySelectorAll(".tb-tool-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const memberId = btn.dataset.memberId;
      const toolId = btn.dataset.toolId;
      toggleMemberTool(memberId, toolId);
      _renderEdit();
    });
  });

  // Delete
  _container.querySelectorAll("[data-delete]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const memberId = btn.dataset.delete;
      if (confirm(t("tb.edit.delete_confirm"))) {
        removeMember(memberId);
        _renderEdit();
      }
    });
  });

  // Add member
  _container.querySelector("[data-action='add']")?.addEventListener("click", () => {
    _showAddModal();
  });

  // Back
  _container.querySelector("[data-action='back']")?.addEventListener("click", () => {
    navigateTo("#/");
  });

  // Chat
  _container.querySelector("[data-action='chat']")?.addEventListener("click", () => {
    navigateTo("#/chat");
  });
}

// ── Add Member Modal ──────────────────────

function _showAddModal() {
  const roleItems = ROLES.map((role) => {
    const icon = ROLE_ICONS[role.id] || "\u{1F464}";
    return `<button class="te-modal-role-item" data-add-role="${role.id}">${icon} ${t(role.nameKey)}</button>`;
  }).join("");

  const overlay = document.createElement("div");
  overlay.className = "te-modal-overlay";
  overlay.innerHTML = `
    <div class="te-modal">
      <div class="te-modal-title">${t("tb.edit.add_title")}</div>
      <div class="te-modal-role-list">
        ${roleItems}
      </div>
      <button class="te-modal-cancel" data-action="cancel">${t("tb.cancel")}</button>
    </div>
  `;

  // Close on overlay click
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.remove();
  });

  overlay.querySelector("[data-action='cancel']")?.addEventListener("click", () => {
    overlay.remove();
  });

  overlay.querySelectorAll("[data-add-role]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const roleId = btn.dataset.addRole;
      addMember(roleId);
      overlay.remove();
      _renderEdit();
    });
  });

  document.body.appendChild(overlay);
}
