/* ── Team Builder — 5-Screen Wizard ───────────
   Screens: 1=Template Select, 2=Member Confirm,
            3=Role Picker, 4=Complete, 5=Team Edit
   ─────────────────────────────────────────────── */

import { t, applyTranslations } from "/shared/i18n.js";
import { escapeHtml } from "../modules/state.js";
import { navigateTo } from "../modules/router.js";
import {
  TEMPLATES,
  ROLES,
  getRoleById,
  getToolLabel,
  getAllTools,
  getTemplateById,
  createTeam,
  getTeam,
  addMember,
  removeMember,
  updateMemberRole,
  toggleMemberTool,
} from "../modules/team-data.js";

// ── Constants ────────────────────────────────

const ROLE_ICONS = {
  secretary: "\uD83D\uDCCB",
  customer_support: "\uD83C\uDFE7",
  back_office: "\uD83D\uDCC1",
  sales_assist: "\uD83D\uDCC8",
  pr_sns: "\uD83D\uDCE3",
  recruiter: "\uD83D\uDC65",
  accounting: "\uD83D\uDCB0",
  project_manager: "\uD83C\uDFAF",
  researcher: "\uD83D\uDD0D",
  content_writer: "\u270D\uFE0F",
};

const TEMPLATE_ICONS = {
  secretary: "\uD83D\uDCCB",
  customer_support: "\uD83C\uDFE7",
  sales_assist: "\uD83D\uDCC8",
  back_office: "\uD83D\uDCC1",
};

const AVATAR_COLORS = [
  "#6366f1", "#ec4899", "#f59e0b", "#10b981",
  "#3b82f6", "#8b5cf6", "#ef4444", "#14b8a6",
  "#f97316", "#06b6d4",
];

// ── State ────────────────────────────────────

const state = {
  currentStep: 1,
  selectedTemplateId: null,
  roleSelections: {},
  prefilled: false,
  createdTeam: null,
};

let _container = null;

// ── Public API (Page Module) ─────────────────

export function render(container) {
  _container = container;
  state.currentStep = 1;
  state.selectedTemplateId = null;
  state.roleSelections = {};
  state.prefilled = false;
  state.createdTeam = null;
  _renderCurrentStep();
}

export function destroy() {
  _container = null;
}

// ── Step Router ──────────────────────────────

function _renderCurrentStep() {
  if (!_container) return;
  switch (state.currentStep) {
    case 1: _renderStep1(); break;
    case 2: _renderStep2(); break;
    case 3: _renderStep3(); break;
    case 4: _renderStep4(); break;
    case 5: _renderStep5(); break;
  }
  applyTranslations();
}

// ── Step Indicator ───────────────────────────

function _stepIndicator(active) {
  const totalSteps = 4;
  const clamp = Math.min(active, totalSteps);
  const parts = [];
  for (let i = 1; i <= totalSteps; i++) {
    let cls = "tb-step-dot";
    if (i === clamp) cls += " active";
    else if (i < clamp) cls += " done";
    parts.push(`<span class="${cls}"></span>`);
    if (i < totalSteps) {
      const connCls = i < clamp ? "tb-step-connector done" : "tb-step-connector";
      parts.push(`<span class="${connCls}"></span>`);
    }
  }
  return `<div class="tb-step-indicator">${parts.join("")}</div>`;
}

// ══════════════════════════════════════════════
// Screen 1: Template Selection
// ══════════════════════════════════════════════

function _renderStep1() {
  const templateCards = TEMPLATES.map((tpl) => {
    const members = tpl.members;
    const totalCount = members.reduce((s, m) => s + m.count, 0);
    const countLabel = totalCount === 1
      ? t("tb.count_one")
      : `${totalCount}${t("tb.count_suffix")}`;
    const recBadge = tpl.recommended
      ? `<span class="tb-template-badge">${escapeHtml(t("tb.recommended"))}</span>`
      : "";
    const cls = tpl.recommended ? "tb-template-card recommended" : "tb-template-card";
    const icon = TEMPLATE_ICONS[tpl.id] || "\uD83D\uDCCB";

    return `
      <div class="${cls}" data-tpl-id="${escapeHtml(tpl.id)}">
        <div class="tb-template-icon">${icon}</div>
        <div class="tb-template-info">
          <div class="tb-template-name">${escapeHtml(t(tpl.nameKey))} ${recBadge}</div>
          <div class="tb-template-desc">${escapeHtml(t(tpl.descKey))}</div>
        </div>
        <div class="tb-template-count">${escapeHtml(countLabel)}</div>
      </div>
    `;
  }).join("");

  const customCard = `
    <div class="tb-template-card" data-action="custom">
      <div class="tb-template-icon">\u2699\uFE0F</div>
      <div class="tb-template-info">
        <div class="tb-template-name">${escapeHtml(t("tb.tpl.custom"))}</div>
        <div class="tb-template-desc">${escapeHtml(t("tb.tpl.custom.desc"))}</div>
      </div>
    </div>
  `;

  _container.innerHTML = `
    <div class="tb-wizard">
      ${_stepIndicator(1)}
      <div class="tb-screen-title">${escapeHtml(t("tb.step1.title"))}</div>
      <div class="tb-screen-desc">${escapeHtml(t("tb.step1.desc"))}</div>
      <div class="tb-template-list">
        ${templateCards}
        ${customCard}
      </div>
      <div style="text-align:center;">
        <button class="tb-skip-link" data-action="skip">${escapeHtml(t("tb.skip"))}</button>
      </div>
    </div>
  `;

  _container.querySelectorAll("[data-tpl-id]").forEach((el) => {
    el.addEventListener("click", () => {
      state.selectedTemplateId = el.dataset.tplId;
      state.currentStep = 2;
      _renderCurrentStep();
    });
  });

  _container.querySelector("[data-action='custom']")?.addEventListener("click", () => {
    state.selectedTemplateId = null;
    state.roleSelections = {};
    state.prefilled = false;
    state.currentStep = 3;
    _renderCurrentStep();
  });

  _container.querySelector("[data-action='skip']")?.addEventListener("click", () => {
    navigateTo("#/");
  });
}

// ══════════════════════════════════════════════
// Screen 2: Member Confirmation
// ══════════════════════════════════════════════

function _renderStep2() {
  const tpl = getTemplateById(state.selectedTemplateId);
  if (!tpl) { state.currentStep = 1; _renderCurrentStep(); return; }

  const memberRows = tpl.members.map((m) => {
    const role = getRoleById(m.roleId);
    if (!role) return "";
    const tools = role.defaultTools.map((tid) => escapeHtml(getToolLabel(tid))).join(" / ");
    const icon = ROLE_ICONS[m.roleId] || "\uD83D\uDC64";
    return `
      <div class="tb-member-card">
        <div class="tb-member-avatar" style="background:${AVATAR_COLORS[0]}">${icon}</div>
        <div class="tb-member-info">
          <div class="tb-member-name">${escapeHtml(t(role.nameKey))} x ${m.count}</div>
          <div class="tb-member-role">${escapeHtml(t("tb.tools"))}: ${tools}</div>
        </div>
      </div>
    `;
  }).join("");

  _container.innerHTML = `
    <div class="tb-wizard">
      ${_stepIndicator(2)}
      <div class="tb-screen-title">${escapeHtml(t(tpl.nameKey))}${escapeHtml(t("tb.step2.title_suffix"))}</div>
      <div class="tb-screen-desc">${escapeHtml(t("tb.step2.desc"))}</div>
      <div class="tb-member-list">
        ${memberRows}
      </div>
      <div class="tb-wizard-nav">
        <button class="btn-secondary" data-action="back">${escapeHtml(t("tb.back"))}</button>
        <div class="tb-wizard-nav-right">
          <button class="btn-secondary" data-action="customize">${escapeHtml(t("tb.step2.customize"))}</button>
          <button class="btn-primary" data-action="create">${escapeHtml(t("tb.step2.create"))}</button>
        </div>
      </div>
    </div>
  `;

  _container.querySelector("[data-action='back']")?.addEventListener("click", () => {
    state.currentStep = 1;
    _renderCurrentStep();
  });

  _container.querySelector("[data-action='customize']")?.addEventListener("click", () => {
    state.roleSelections = {};
    for (const m of tpl.members) {
      state.roleSelections[m.roleId] = m.count;
    }
    state.prefilled = true;
    state.currentStep = 3;
    _renderCurrentStep();
  });

  _container.querySelector("[data-action='create']")?.addEventListener("click", () => {
    const selections = tpl.members.map((m) => ({ roleId: m.roleId, count: m.count }));
    state.createdTeam = createTeam(selections);
    state.currentStep = 4;
    _renderCurrentStep();
  });
}

// ══════════════════════════════════════════════
// Screen 3: Role Pickup
// ══════════════════════════════════════════════

function _renderStep3() {
  const roleItems = ROLES.map((role) => {
    const selected = state.roleSelections[role.id] != null;
    const count = state.roleSelections[role.id] || 1;
    const icon = ROLE_ICONS[role.id] || "\uD83D\uDC64";
    const cls = selected ? "tb-role-item selected" : "tb-role-item";
    const toolTags = role.defaultTools.map((tid) =>
      `<span class="tb-tool-tag">${escapeHtml(getToolLabel(tid))}</span>`
    ).join("");

    const options = [1, 2, 3].map((n) =>
      `<option value="${n}" ${n === count ? "selected" : ""}>${n}${escapeHtml(t("tb.count_suffix"))}</option>`
    ).join("");

    return `
      <div class="${cls}" data-role-id="${escapeHtml(role.id)}">
        <div class="tb-role-checkbox">\u2713</div>
        <div class="tb-role-info">
          <div class="tb-role-name">${icon} ${escapeHtml(t(role.nameKey))}</div>
          <div class="tb-role-desc">${escapeHtml(t(role.descKey))}</div>
          <div class="tb-role-tools">${toolTags}</div>
        </div>
        <select class="tb-role-count-select" data-count-for="${escapeHtml(role.id)}" ${selected ? "" : 'style="visibility:hidden"'}>
          ${options}
        </select>
      </div>
    `;
  }).join("");

  const hasSelection = Object.keys(state.roleSelections).length > 0;

  _container.innerHTML = `
    <div class="tb-wizard">
      ${_stepIndicator(3)}
      <div class="tb-screen-title">${escapeHtml(t("tb.step3.title"))}</div>
      <div class="tb-screen-desc">${escapeHtml(t("tb.step3.desc"))}</div>
      <div class="tb-role-grid">
        ${roleItems}
      </div>
      <div class="tb-wizard-nav">
        <button class="btn-secondary" data-action="back">${escapeHtml(t("tb.back"))}</button>
        <button class="btn-primary" data-action="create" ${hasSelection ? "" : "disabled"}>${escapeHtml(t("tb.step3.create"))}</button>
      </div>
    </div>
  `;

  // Role toggle
  _container.querySelectorAll(".tb-role-item").forEach((el) => {
    el.addEventListener("click", (e) => {
      if (e.target.tagName === "SELECT" || e.target.tagName === "OPTION") return;
      const roleId = el.dataset.roleId;
      if (state.roleSelections[roleId] != null) {
        delete state.roleSelections[roleId];
      } else {
        state.roleSelections[roleId] = 1;
      }
      _renderCurrentStep();
    });
  });

  // Count selects
  _container.querySelectorAll(".tb-role-count-select").forEach((sel) => {
    sel.addEventListener("change", (e) => {
      const roleId = sel.dataset.countFor;
      if (state.roleSelections[roleId] != null) {
        state.roleSelections[roleId] = parseInt(e.target.value, 10);
      }
    });
    sel.addEventListener("click", (e) => e.stopPropagation());
  });

  // Back
  _container.querySelector("[data-action='back']")?.addEventListener("click", () => {
    if (state.selectedTemplateId) {
      state.currentStep = 2;
    } else {
      state.currentStep = 1;
    }
    _renderCurrentStep();
  });

  // Create
  _container.querySelector("[data-action='create']")?.addEventListener("click", () => {
    const selections = Object.entries(state.roleSelections).map(([roleId, count]) => ({
      roleId,
      count,
    }));
    if (selections.length === 0) return;
    state.createdTeam = createTeam(selections);
    state.currentStep = 4;
    _renderCurrentStep();
  });
}

// ══════════════════════════════════════════════
// Screen 4: Creation Complete
// ══════════════════════════════════════════════

function _renderStep4() {
  const team = state.createdTeam;
  if (!team || !team.members) {
    state.currentStep = 1;
    _renderCurrentStep();
    return;
  }

  const memberCards = team.members.map((m, idx) => {
    const role = getRoleById(m.roleId);
    const roleName = role ? t(role.nameKey) : m.roleId;
    const color = AVATAR_COLORS[idx % AVATAR_COLORS.length];
    const initial = escapeHtml(m.displayName.charAt(0));
    const toolTags = m.tools.map((tid) =>
      `<span class="tb-tool-tag">${escapeHtml(getToolLabel(tid))}</span>`
    ).join("");

    return `
      <div class="tb-member-card">
        <div class="tb-member-avatar" style="background:${color}">${initial}</div>
        <div class="tb-member-info">
          <div class="tb-member-name">${escapeHtml(roleName)}: ${escapeHtml(m.displayName)}</div>
          <div class="tb-member-tools-row">${toolTags}</div>
        </div>
      </div>
    `;
  }).join("");

  _container.innerHTML = `
    <div class="tb-wizard">
      ${_stepIndicator(4)}
      <div class="tb-complete-icon">\uD83C\uDF89</div>
      <div class="tb-complete-title">${escapeHtml(t("tb.step4.title"))}</div>
      <div class="tb-member-list">
        ${memberCards}
      </div>
      <div class="tb-wizard-nav" style="justify-content:center;">
        <button class="btn-primary" data-action="chat">${escapeHtml(t("tb.step4.chat"))}</button>
        <button class="btn-secondary" data-action="edit">${escapeHtml(t("tb.step4.edit"))}</button>
      </div>
    </div>
  `;

  _container.querySelector("[data-action='chat']")?.addEventListener("click", () => {
    navigateTo("#/chat");
  });

  _container.querySelector("[data-action='edit']")?.addEventListener("click", () => {
    state.currentStep = 5;
    _renderCurrentStep();
  });
}

// ══════════════════════════════════════════════
// Screen 5: Team Edit
// ══════════════════════════════════════════════

function _renderStep5() {
  const team = state.createdTeam || getTeam();
  if (!team || !team.members) {
    state.currentStep = 1;
    _renderCurrentStep();
    return;
  }
  state.createdTeam = team;

  _container.innerHTML = `
    <div class="tb-wizard">
      <div class="tb-screen-title">${escapeHtml(t("tb.step5.title"))}</div>
      <div class="tb-screen-desc">${escapeHtml(t("tb.step5.desc"))}</div>
      <div class="tb-edit-section" id="tbEditMembers"></div>
      <button class="tb-add-member-btn" id="tbAddMemberBtn">+ ${escapeHtml(t("tb.step5.add_member"))}</button>
      <div id="tbAddMemberPicker" style="display:none;"></div>
      <div class="tb-wizard-nav" style="margin-top:16px;">
        <button class="btn-secondary" data-action="back">${escapeHtml(t("tb.back"))}</button>
        <button class="btn-primary" data-action="done">${escapeHtml(t("tb.step5.done"))}</button>
      </div>
    </div>
  `;

  _renderEditMembers();

  document.getElementById("tbAddMemberBtn")?.addEventListener("click", () => {
    _toggleAddPicker();
  });

  _container.querySelector("[data-action='back']")?.addEventListener("click", () => {
    state.currentStep = 4;
    _renderCurrentStep();
  });

  _container.querySelector("[data-action='done']")?.addEventListener("click", () => {
    navigateTo("#/");
  });
}

/** Render the editable member list inside #tbEditMembers */
function _renderEditMembers() {
  const section = document.getElementById("tbEditMembers");
  if (!section) return;

  const team = state.createdTeam;
  if (!team || !team.members) { section.innerHTML = ""; return; }

  const allTools = getAllTools();

  const cards = team.members.map((m, idx) => {
    const color = AVATAR_COLORS[idx % AVATAR_COLORS.length];
    const initial = escapeHtml(m.displayName.charAt(0));

    const roleSelect = ROLES.map((r) =>
      `<option value="${escapeHtml(r.id)}" ${r.id === m.roleId ? "selected" : ""}>${escapeHtml(t(r.nameKey))}</option>`
    ).join("");

    const toolToggles = allTools.map((tool) => {
      const isActive = m.tools.includes(tool.id);
      return `<button class="tb-tool-toggle ${isActive ? "active" : ""}" data-tool="${escapeHtml(tool.id)}" data-member-id="${escapeHtml(m.id)}">${isActive ? "\u2713 " : ""}${escapeHtml(tool.label)}</button>`;
    }).join("");

    return `
      <div class="tb-member-card">
        <div class="tb-member-avatar" style="background:${color}">${initial}</div>
        <div class="tb-member-info">
          <div class="tb-member-name">${escapeHtml(m.displayName)}</div>
          <div style="margin-top:6px;">
            <select class="tb-role-select" data-member-id="${escapeHtml(m.id)}">${roleSelect}</select>
          </div>
          <div class="tb-member-tools-row" style="margin-top:6px;">${toolToggles}</div>
        </div>
        <div class="tb-member-actions">
          <button class="tb-btn-icon danger" data-delete-id="${escapeHtml(m.id)}" title="${escapeHtml(t("tb.step5.delete"))}">\u2715</button>
        </div>
      </div>
    `;
  }).join("");

  section.innerHTML = `<div class="tb-member-list">${cards}</div>`;

  // Role changes
  section.querySelectorAll(".tb-role-select").forEach((sel) => {
    sel.addEventListener("change", (e) => {
      updateMemberRole(sel.dataset.memberId, e.target.value);
      state.createdTeam = getTeam();
      _renderEditMembers();
    });
  });

  // Tool toggles
  section.querySelectorAll(".tb-tool-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      toggleMemberTool(btn.dataset.memberId, btn.dataset.tool);
      state.createdTeam = getTeam();
      _renderEditMembers();
    });
  });

  // Delete
  section.querySelectorAll("[data-delete-id]").forEach((btn) => {
    btn.addEventListener("click", () => {
      removeMember(btn.dataset.deleteId);
      state.createdTeam = getTeam();
      _renderEditMembers();
    });
  });
}

/** Toggle the add-member role picker */
function _toggleAddPicker() {
  const picker = document.getElementById("tbAddMemberPicker");
  if (!picker) return;

  if (picker.style.display !== "none") {
    picker.style.display = "none";
    picker.innerHTML = "";
    return;
  }

  let html = '<div class="card" style="margin-top:12px;"><div class="card-header">' +
    escapeHtml(t("tb.step5.pick_role")) +
    '</div><div class="card-body" style="display:flex;flex-wrap:wrap;gap:8px;">';

  for (const role of ROLES) {
    const icon = ROLE_ICONS[role.id] || "";
    html += `<button class="btn-secondary" data-add-role="${escapeHtml(role.id)}">${icon} ${escapeHtml(t(role.nameKey))}</button>`;
  }

  html += "</div></div>";
  picker.innerHTML = html;
  picker.style.display = "block";

  picker.querySelectorAll("[data-add-role]").forEach((btn) => {
    btn.addEventListener("click", () => {
      addMember(btn.dataset.addRole);
      state.createdTeam = getTeam();
      picker.style.display = "none";
      picker.innerHTML = "";
      _renderEditMembers();
    });
  });
}
