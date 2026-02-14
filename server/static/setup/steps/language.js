/* ── Step 1: Language Selection ────────────── */

import { t, setLocale, getLocale } from "../setup.js";

let container = null;
let selectedLang = "ja";

const LANGUAGES = [
  { code: "ja", name: "Japanese", native: "\u65e5\u672c\u8a9e", flag: "\ud83c\uddef\ud83c\uddf5" },
  { code: "en", name: "English", native: "English", flag: "\ud83c\uddfa\ud83c\uddf8" },
];

const PREVIEWS = {
  ja: "AnimaWorks\u306f\u3001AI\u30a8\u30fc\u30b8\u30a7\u30f3\u30c8\u3092\u300c\u81ea\u5f8b\u7684\u306a\u4eba\u300d\u3068\u3057\u3066\u6271\u3046\u30d5\u30ec\u30fc\u30e0\u30ef\u30fc\u30af\u3067\u3059\u3002\u5404Person\u306f\u56fa\u6709\u306e\u30a2\u30a4\u30c7\u30f3\u30c6\u30a3\u30c6\u30a3\u30fb\u8a18\u61b6\u30fb\u5224\u65ad\u57fa\u6e96\u3092\u6301\u3061\u307e\u3059\u3002",
  en: "AnimaWorks is a framework that treats AI agents as \"autonomous persons\". Each Person has their own identity, memories, and decision-making criteria.",
};

export function initLanguageStep(el) {
  container = el;

  // Auto-detect locale from server
  detectLocale();

  render();
}

async function detectLocale() {
  try {
    const res = await fetch("/api/setup/detect-locale");
    if (res.ok) {
      const data = await res.json();
      if (data.detected && LANGUAGES.some((l) => l.code === data.detected)) {
        selectedLang = data.detected;
        setLocale(selectedLang);
        render();
      }
    }
  } catch {
    // Use default
  }
}

function render() {
  const langCards = LANGUAGES.map((lang) => {
    const selected = lang.code === selectedLang ? " selected" : "";
    return `
      <div class="language-card${selected}" data-lang="${lang.code}">
        <div class="language-flag">${lang.flag}</div>
        <div class="language-info">
          <div class="language-name">${lang.name}</div>
          <div class="language-native">${lang.native}</div>
        </div>
      </div>
    `;
  }).join("");

  const preview = PREVIEWS[selectedLang] || PREVIEWS.ja;

  container.innerHTML = `
    <h2 data-i18n="lang.title">${t("lang.title")}</h2>
    <p style="color: #8888aa; font-size: 0.85rem; margin-top: 4px;" data-i18n="lang.desc">${t("lang.desc")}</p>
    <div class="language-options">
      ${langCards}
    </div>
    <div class="language-preview">
      <div class="language-preview-title" data-i18n="lang.preview.title">${t("lang.preview.title")}</div>
      <div class="language-preview-text">${preview}</div>
    </div>
  `;

  // Bind click handlers
  container.querySelectorAll(".language-card").forEach((card) => {
    card.addEventListener("click", () => {
      selectedLang = card.dataset.lang;
      setLocale(selectedLang);
      render();
    });
  });
}

export function getLanguageData() {
  return { locale: selectedLang };
}
