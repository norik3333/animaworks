"""Tests for type-safety improvements (Issue: 20260225_type-safety-improvements).

Validates Protocol conformance, TypedDict field parity,
and ImageData type consistency across layers.
"""
from __future__ import annotations

from dataclasses import dataclass


class TestSessionResultLikeProtocol:
    """Verify SessionResultLike Protocol contract."""

    def test_protocol_satisfied_by_mock(self):
        from core.execution.base import SessionResultLike

        @dataclass
        class FakeResult:
            num_turns: int = 5
            session_id: str = "abc"

        assert isinstance(FakeResult(), SessionResultLike)

    def test_none_is_not_session_result_like(self):
        from core.execution.base import SessionResultLike

        assert not isinstance(None, SessionResultLike)

    def test_execution_result_accepts_none(self):
        from core.execution.base import ExecutionResult

        r = ExecutionResult(text="hello")
        assert r.result_message is None

    def test_execution_result_accepts_protocol(self):
        from core.execution.base import ExecutionResult, SessionResultLike

        @dataclass
        class FakeResult:
            num_turns: int = 3
            session_id: str = "s1"

        r = ExecutionResult(text="hello", result_message=FakeResult())
        assert isinstance(r.result_message, SessionResultLike)
        assert r.result_message.num_turns == 3


class TestImageDataTypedDict:
    """Verify ImageData TypedDict usage."""

    def test_image_data_in_cycle_result(self):
        from core.schemas import CycleResult, ImageData

        img: ImageData = {"data": "base64==", "media_type": "image/png"}
        r = CycleResult(trigger="test", action="ok", images=[img])
        assert r.images[0]["media_type"] == "image/png"

    def test_image_data_matches_image_attachment(self):
        """ImageData keys should be a subset of ImageAttachment fields."""
        from typing import get_type_hints

        from core.schemas import ImageData

        td_keys = set(get_type_hints(ImageData).keys())
        assert "data" in td_keys
        assert "media_type" in td_keys


class TestProcessSupervisorLikeProtocol:
    """Verify ProcessSupervisorLike Protocol."""

    def test_protocol_satisfied(self):
        from core.tooling.handler import ProcessSupervisorLike

        class FakeSupervisor:
            def get_process_status(self, anima_name: str) -> dict:
                return {"status": "running"}

        assert isinstance(FakeSupervisor(), ProcessSupervisorLike)

    def test_non_conforming_rejected(self):
        from core.tooling.handler import ProcessSupervisorLike

        class NotASupervisor:
            pass

        assert not isinstance(NotASupervisor(), ProcessSupervisorLike)


class TestLastRotationDateType:
    """Verify _last_rotation_date type change."""

    def test_initial_value_is_none(self):
        import importlib

        import core._agent_prompt_log as mod
        importlib.reload(mod)
        assert mod._last_rotation_date is None

    def test_rotation_sets_date_string(self, tmp_path):
        import core._agent_prompt_log as mod

        mod._last_rotation_date = None
        log_dir = tmp_path / "prompt_logs"
        log_dir.mkdir()
        mod._rotate_prompt_logs(log_dir)
        assert isinstance(mod._last_rotation_date, str)
        assert len(mod._last_rotation_date) == 10  # YYYY-MM-DD
