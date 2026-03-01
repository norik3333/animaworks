/**
 * Avatar asset resolver — returns the right filenames based on business mode.
 *
 * When the "business" theme is active (`.theme-business` on `<body>`),
 * realistic variants (`_realistic.png`) are tried first with anime
 * fallback. In default theme, anime assets are tried first.
 */

export function isBusinessMode() {
  return document.body.classList.contains("theme-business");
}

/**
 * Return ordered bustup candidates for probing (HEAD request).
 * Business mode → realistic first, then anime fallback.
 */
export function bustupCandidates() {
  if (isBusinessMode()) {
    return [
      "avatar_bustup_realistic.png",
      "avatar_bustup.png",
      "avatar_chibi.png",
    ];
  }
  return ["avatar_bustup.png", "avatar_chibi.png"];
}

/**
 * Return ordered bustup expression filename candidates.
 * @param {string} expression - e.g. "neutral", "smile", "troubled"
 */
export function bustupExpressionCandidates(expression) {
  const anime =
    expression === "neutral"
      ? "avatar_bustup.png"
      : `avatar_bustup_${expression}.png`;
  const realistic =
    expression === "neutral"
      ? "avatar_bustup_realistic.png"
      : `avatar_bustup_${expression}_realistic.png`;
  if (isBusinessMode()) {
    return [realistic, anime];
  }
  return [anime];
}

/**
 * Build the asset URL for a given anima name and filename.
 */
export function assetUrl(animaName, filename) {
  return `/api/animas/${encodeURIComponent(animaName)}/assets/${encodeURIComponent(filename)}`;
}

/**
 * Probe candidates via HEAD and return the first available URL (or null).
 * @param {string} animaName
 * @param {string[]} candidates - list of filenames to try
 * @returns {Promise<string|null>}
 */
export async function resolveAvatar(animaName, candidates) {
  for (const filename of candidates) {
    const url = assetUrl(animaName, filename);
    try {
      const resp = await fetch(url, { method: "HEAD" });
      if (resp.ok) return url;
    } catch {
      /* network error — try next */
    }
  }
  return null;
}
