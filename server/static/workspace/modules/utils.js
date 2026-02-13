// ── Shared Utilities ──────────────────────
// Common helpers used across workspace modules.

/**
 * Escape HTML special characters to prevent XSS.
 */
export function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

/**
 * Lightweight Markdown → HTML renderer.
 * Escapes HTML first, then applies safe transforms.
 */
export function renderSimpleMarkdown(text) {
  if (!text) return "";

  let html = escapeHtml(text);

  // Fenced code blocks: ```lang\n...\n```
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_m, _lang, code) => {
    return `<pre class="md-code-block"><code>${code}</code></pre>`;
  });

  // Inline code: `...`
  html = html.replace(/`([^`]+)`/g, '<code class="md-code-inline">$1</code>');

  // Bold: **...**
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

  // Italic: *...*
  html = html.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, "<em>$1</em>");

  // Links: [text](url) — only allow http/https to prevent javascript: XSS
  html = html.replace(
    /\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>'
  );

  // Unordered list items
  html = html.replace(/^(?:[-*]) (.+)$/gm, "<li>$1</li>");
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, "<ul>$1</ul>");

  // Line breaks (outside of pre blocks)
  html = html.replace(
    /(<pre[\s\S]*?<\/pre>)|(\n)/g,
    (_m, pre, nl) => (pre ? pre : nl ? "<br>" : "")
  );

  return html;
}

/**
 * Format an ISO timestamp to HH:MM (ja-JP).
 */
export function timeStr(isoOrTs) {
  if (!isoOrTs) return "--:--";
  const d = new Date(isoOrTs);
  if (isNaN(d.getTime())) return "--:--";
  return d.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit" });
}

/**
 * Strip .md extension from filename for display.
 */
export function stripMdExtension(filename) {
  return filename.replace(/\.md$/, "");
}
