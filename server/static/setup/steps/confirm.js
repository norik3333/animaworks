/* ── Step 4: Confirmation ──────────────────── */

import { t, goToStep } from "../setup.js";

let confirmPanel = null;

export function initConfirmStep(panel) {
  confirmPanel = panel;

  panel.innerHTML = `
    <h2 class="step-section-title">${t("confirm.title")}</h2>
    <p class="step-section-desc">${t("confirm.desc")}</p>
    <div class="card" id="confirmSummary"></div>
  `;
}

export function populateConfirm(data) {
  if (!confirmPanel) return;

  const locale = data.language?.locale || "ja";
  const provider = data.environment?.provider || "-";
  const template = data.character?.template || "-";
  const personName = data.character?.person_config?.name || template || "-";
  const imageKeys = data.environment?.image_keys || {};

  // Build API key summary rows
  const keyEntries = Object.entries(imageKeys).filter(([, v]) => v);
  const keySummary = keyEntries.length > 0
    ? keyEntries.map(([k, v]) => `
        <div class="summary-row">
          <span class="summary-key">${k}</span>
          <span class="summary-val masked">${maskKey(v)}</span>
        </div>
      `).join("")
    : `<div class="summary-row">
        <span class="summary-key">${t("confirm.apikeys")}</span>
        <span class="summary-val">${t("confirm.not_configured")}</span>
      </div>`;

  confirmPanel.innerHTML = `
    <h2 class="step-section-title">${t("confirm.title")}</h2>
    <p class="step-section-desc">${t("confirm.desc")}</p>

    <div class="card">
      <div class="summary-section">
        <div class="summary-title">${t("confirm.language")}
          <button class="btn-edit-step" data-step="0">${t("confirm.edit")}</button>
        </div>
        <div class="summary-row">
          <span class="summary-key">${t("confirm.language")}</span>
          <span class="summary-val">${locale === "ja" ? t("lang.ja") : t("lang.en")}</span>
        </div>
      </div>

      <div class="summary-section">
        <div class="summary-title">${t("confirm.provider")}
          <button class="btn-edit-step" data-step="1">${t("confirm.edit")}</button>
        </div>
        <div class="summary-row">
          <span class="summary-key">${t("confirm.provider")}</span>
          <span class="summary-val">${t(`env.provider.${provider}`) || provider}</span>
        </div>
        ${keySummary}
      </div>

      <div class="summary-section">
        <div class="summary-title">${t("confirm.person")}
          <button class="btn-edit-step" data-step="2">${t("confirm.edit")}</button>
        </div>
        <div class="summary-row">
          <span class="summary-key">${t("confirm.template")}</span>
          <span class="summary-val">${template}</span>
        </div>
        <div class="summary-row">
          <span class="summary-key">${t("confirm.person")}</span>
          <span class="summary-val">${personName}</span>
        </div>
      </div>
    </div>
  `;

  // Wire up edit buttons
  confirmPanel.querySelectorAll(".btn-edit-step").forEach((btn) => {
    btn.addEventListener("click", () => {
      const step = parseInt(btn.dataset.step, 10);
      goToStep(step);
    });
  });
}

export async function completeSetup(data) {
  if (!confirmPanel) return;

  try {
    const res = await fetch("/api/setup/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || t("confirm.error"));
    }

    // Show success screen
    confirmPanel.innerHTML = `
      <div class="completion-screen">
        <div class="completion-icon">\u2705</div>
        <h2 class="completion-title">${t("confirm.success")}</h2>
        <p class="completion-desc">${t("confirm.success.desc")}</p>
      </div>
    `;

    // Hide nav buttons
    const nav = document.querySelector(".step-nav");
    if (nav) nav.style.display = "none";

    // Redirect to dashboard after a short delay
    setTimeout(() => {
      window.location.href = "/";
    }, 2000);
  } catch (e) {
    const errorDiv = confirmPanel.querySelector("#confirmError") || document.createElement("div");
    errorDiv.id = "confirmError";
    errorDiv.innerHTML = `<div class="error-message">${e.message || t("confirm.error")}</div>`;
    if (!confirmPanel.querySelector("#confirmError")) {
      confirmPanel.appendChild(errorDiv);
    }
    throw e;
  }
}

function maskKey(key) {
  if (!key || key.length < 8) return "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022";
  return key.slice(0, 4) + "\u2022".repeat(Math.min(key.length - 8, 16)) + key.slice(-4);
}
