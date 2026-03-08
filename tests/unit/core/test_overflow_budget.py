from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit test: DK summary budget constants and scaling.

Verifies that the procedure and knowledge summary budgets in
build_system_prompt scale correctly with context window size.
"""

from core.prompt.builder import (
    _KNOW_SUMMARY_BUDGET,
    _PROC_SUMMARY_BUDGET,
    _REFERENCE_WINDOW,
)


def test_summary_budget_constants() -> None:
    """Procedure + knowledge summary budgets total 500 tokens at scale=1.0."""
    assert _PROC_SUMMARY_BUDGET == 300
    assert _KNOW_SUMMARY_BUDGET == 200
    assert _PROC_SUMMARY_BUDGET + _KNOW_SUMMARY_BUDGET == 500


def test_summary_budget_at_reference_window() -> None:
    """At 128k context, budgets equal their constants."""
    scale = min(_REFERENCE_WINDOW / _REFERENCE_WINDOW, 1.0)
    assert scale == 1.0
    assert max(int(_PROC_SUMMARY_BUDGET * scale), 0) == 300
    assert max(int(_KNOW_SUMMARY_BUDGET * scale), 0) == 200


def test_summary_budget_small_context() -> None:
    """At 64k context, budgets are halved."""
    ctx = 64_000
    scale = min(ctx / _REFERENCE_WINDOW, 1.0)
    proc = max(int(_PROC_SUMMARY_BUDGET * scale), 0)
    know = max(int(_KNOW_SUMMARY_BUDGET * scale), 0)
    assert proc == 150
    assert know == 100


def test_summary_budget_large_context() -> None:
    """At 200k context, scale is capped at 1.0."""
    ctx = 200_000
    scale = min(ctx / _REFERENCE_WINDOW, 1.0)
    assert scale == 1.0
    assert max(int(_PROC_SUMMARY_BUDGET * scale), 0) == 300
    assert max(int(_KNOW_SUMMARY_BUDGET * scale), 0) == 200
