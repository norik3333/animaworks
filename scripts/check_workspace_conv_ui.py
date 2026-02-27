#!/usr/bin/env python3
"""Verify workspace conversation overlay: input area size and 2x2 icon layout."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from playwright.sync_api import sync_playwright

PORTS = [18500, 8000]  # default animaworks port first
OUTPUT = Path("/tmp/animaworks-ws-conv-overlay.png")


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        url = None
        for port in PORTS:
            try:
                u = f"http://localhost:{port}/workspace/"
                page.goto(u, wait_until="domcontentloaded", timeout=5000)
                url = u
                break
            except Exception:
                try:
                    u = f"http://127.0.0.1:{port}/workspace/"
                    page.goto(u, wait_until="domcontentloaded", timeout=5000)
                    url = u
                    break
                except Exception:
                    continue

        if not url:
            print("ERROR: Could not connect to workspace (tried localhost and 127.0.0.1 on 8000, 18500)")
            browser.close()
            sys.exit(1)

        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2500)

        # Workspace login: Guest or first user button (no username/password)
        guest_btn = page.locator("#wsGuestLoginBtn, button.btn-guest").first
        user_btn = page.locator(".user-btn").first
        if guest_btn.count() > 0 and guest_btn.is_visible():
            guest_btn.click()
            page.wait_for_timeout(1500)
        elif user_btn.count() > 0 and user_btn.is_visible():
            user_btn.click()
            page.wait_for_timeout(1500)

        # Wait for dashboard (hidden class removed after login)
        page.wait_for_selector("#wsDashboard:not(.hidden)", state="visible", timeout=10000)
        page.wait_for_timeout(1500)

        # Open conversation overlay by selecting first Anima from dropdown
        dropdown = page.locator("#wsAnimaDropdown, select.anima-dropdown").first
        if dropdown.count() > 0:
            options = dropdown.locator("option:not([disabled]):not([value=''])")
            opts = [o.get_attribute("value") for o in options.all() if o.get_attribute("value")]
            if opts:
                dropdown.select_option(value=opts[0])
                page.wait_for_timeout(1500)
            else:
                # Try clicking first non-disabled option if select didn't work
                first = dropdown.locator("option").nth(1)
                if first.count() > 0:
                    dropdown.select_option(index=1)
                    page.wait_for_timeout(1500)

        # Wait for conversation overlay to be visible
        overlay = page.locator(".ws-conv-overlay:not(.hidden)")
        overlay.wait_for(state="visible", timeout=5000)
        page.wait_for_timeout(800)

        # Screenshot the full overlay
        page.screenshot(path=OUTPUT, full_page=False)

        # Screenshot input area only
        input_area = page.locator(".ws-conv-input-area").first
        input_out = Path("/tmp/animaworks-ws-input-area.png")
        if input_area.count() > 0:
            input_area.screenshot(path=str(input_out))

        # Inspect layout (direct children only)
        actions = page.locator(".chat-input-actions").first
        textarea = page.locator(".ws-conv-input").first

        issues = []
        if actions.count() > 0:
            n = page.evaluate(
                """() => {
                const el = document.querySelector('.chat-input-actions');
                return el ? el.children.length : 0;
            }"""
            )
            if n != 4:
                issues.append(f"Right icons: expected 4 direct children for 2x2, got {n}")
            # Check computed grid
            grid_cols = page.evaluate(
                """() => {
                const el = document.querySelector('.chat-input-actions');
                if (!el) return null;
                const s = getComputedStyle(el);
                return { display: s.display, gridTemplateColumns: s.gridTemplateColumns };
            }"""
            )
            if grid_cols:
                if "grid" not in (grid_cols.get("display") or ""):
                    issues.append(f"Right icons: display={grid_cols.get('display')} (expected grid)")
        else:
            issues.append("chat-input-actions not found")

        if textarea.count() > 0:
            rect = textarea.bounding_box()
            if rect:
                h = rect.get("height", 0)
                if h < 80:
                    issues.append(f"Input height: {h:.0f}px (expected ~112px min)")
        else:
            issues.append("ws-conv-input (textarea) not found")

        browser.close()

    print(f"Screenshot: {OUTPUT}")
    if input_out.exists():
        print(f"Input area: {input_out}")
    if issues:
        print("\n--- Issues ---")
        for i in issues:
            print(f"  - {i}")
    else:
        print("\nLayout OK: 2x2 icons, input area sufficient")


if __name__ == "__main__":
    main()
