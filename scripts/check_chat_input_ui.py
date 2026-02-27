#!/usr/bin/env python3
"""Verify #/chat input area: height and 2x2 icon layout."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from playwright.sync_api import sync_playwright

PORTS = [8000, 18500]
OUTPUT = Path("/tmp/animaworks-chat-input.png")


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        url = None
        for base in ("http://localhost:18500/#/chat", "http://127.0.0.1:18500/#/chat",
                     "http://localhost:8000/#/chat", "http://127.0.0.1:8000/#/chat"):
            try:
                page.goto(base, wait_until="domcontentloaded", timeout=10000)
                url = base
                break
            except Exception:
                continue

        if not url:
            print("ERROR: Could not connect (tried localhost and 127.0.0.1 on 8000, 18500)")
            browser.close()
            sys.exit(1)

        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Login if form visible (main app uses username/password)
        # Set ANIMAWORKS_USER and ANIMAWORKS_PASS env for localhost:18500/#/chat
        login_form = page.locator("#loginForm, .login-form").first
        if login_form.count() > 0 and login_form.is_visible():
            user = os.environ.get("ANIMAWORKS_USER", "taka")
            pw = os.environ.get("ANIMAWORKS_PASS", "")
            if not pw:
                print("WARN: ANIMAWORKS_PASS not set - login will fail. Set it for #/chat verification.")
            page.fill("#loginUsername, input[placeholder*='ユーザー'], input[name='username']", user)
            page.fill("#loginPassword, input[placeholder*='パスワード'], input[type='password']", pw)
            page.click("button.btn-login, button[type='submit']")
            page.wait_for_timeout(3000)
            # Ensure we're on chat route
            if "/chat" not in page.url:
                page.goto(url, wait_until="networkidle")
                page.wait_for_timeout(2000)

        # Wait for chat page (router loads async); if login showed, we may need more time
        try:
            page.wait_for_selector(".chat-page-layout, #chatPageForm, .chat-input-wrap", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(2500)  # animas API + render

        # Select Anima: click add-conversation then first available item
        add_btn = page.locator("#chatAddConversationBtn").first
        if add_btn.count() > 0 and add_btn.is_visible():
            add_btn.click()
            page.wait_for_timeout(1200)
            item = page.locator(".chat-add-conversation-item[data-anima]:not(.disabled)").first
            if item.count() > 0:
                item.click()
                page.wait_for_timeout(2000)
            else:
                add_btn.click()
                page.wait_for_timeout(500)

        # Fallback: click first anima tab if it exists and input still disabled
        tab = page.locator(".anima-tab").first
        if tab.count() > 0 and tab.is_visible():
            input_el = page.locator("#chatPageInput").first
            if input_el.count() > 0 and input_el.get_attribute("disabled"):
                tab.click()
                page.wait_for_timeout(1500)

        # Proceed to screenshot regardless of input state
        try:
            page.wait_for_selector("#chatPageInput:not([disabled])", timeout=4000)
        except Exception:
            pass
        page.wait_for_timeout(600)

        # Screenshot full page
        page.screenshot(path=OUTPUT, full_page=False)

        # Screenshot input area only
        form = page.locator("#chatPageForm, .chat-input-form").first
        input_out = Path("/tmp/animaworks-chat-input-area.png")
        if form.count() > 0:
            form.screenshot(path=str(input_out))

        # Inspect layout (works even when input disabled)
        result = page.evaluate(
            """() => {
            const form = document.getElementById('chatPageForm') || document.querySelector('.chat-input-form');
            const wrap = form?.querySelector('.chat-input-wrap');
            const textarea = document.getElementById('chatPageInput') || form?.querySelector('.chat-input');
            const actions = form?.querySelector('.chat-input-actions');

            const out = { ok: false, issues: [], classes: [], layout: {} };

            if (!form) { out.issues.push('chatPageForm not found'); return out; }
            out.classes.push('chat-input-form');

            if (!wrap) { out.issues.push('chat-input-wrap not found'); }
            else { out.classes.push('chat-input-wrap'); }

            if (textarea) {
                out.classes.push('chat-input');
                const r = textarea.getBoundingClientRect();
                out.layout.inputHeight = Math.round(r.height);
                const s = getComputedStyle(textarea);
                out.layout.inputMinHeight = s.minHeight;
            }
            if (actions) {
                out.classes.push('chat-input-actions');
                out.layout.actionChildren = actions.children.length;
                const s = getComputedStyle(actions);
                out.layout.actionDisplay = s.display;
                out.layout.actionGridCols = s.gridTemplateColumns;
                if (actions.children.length === 4) out.ok = true;
                else out.issues.push('expected 4 children, got ' + actions.children.length);
            }
            if (textarea && actions && out.layout.inputHeight < 80) {
                out.issues.push('input height ' + out.layout.inputHeight + 'px (expected ~112+)');
            }
            if (out.issues.length === 0 && out.layout.actionChildren === 4) out.ok = true;
            return out;
        }"""
        )

        browser.close()

    print(f"Screenshot: {OUTPUT}")
    if input_out.exists():
        print(f"Input area: {input_out}")

    if result.get("ok"):
        print("\nLayout OK: 入力欄十分、右アイコン2x2")
    else:
        print("\n--- 期待どおりでない場合の情報 ---")
        print("DOM class名:", result.get("classes", []))
        print("表示状態:")
        for k, v in result.get("layout", {}).items():
            print(f"  {k}: {v}")
        if result.get("issues"):
            print("不足点:")
            for i in result["issues"]:
                print(f"  - {i}")


if __name__ == "__main__":
    main()
