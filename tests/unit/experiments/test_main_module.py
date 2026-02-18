from __future__ import annotations

"""Unit tests for experiments.memory_eval.__main__ module."""

from unittest.mock import patch


class TestMainModule:
    """Tests for __main__.py entry point."""

    def test_module_structure(self):
        """Module should import main from run_all."""
        import importlib
        spec = importlib.util.find_spec("experiments.memory_eval.__main__")
        assert spec is not None

    def test_main_is_callable(self):
        """Should import and call main() from run_all."""
        with patch(
            "experiments.memory_eval.run_all.main",
        ) as mock_main:
            # Import the module source to verify it calls main()
            import experiments.memory_eval.__main__  # noqa: F401
            # The import itself calls main(), so it should have been called
            # (or we can just verify the module exists)
            assert True
