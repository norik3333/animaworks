from __future__ import annotations

"""Unit tests for run_all.py orchestration module."""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def dataset_dir(tmp_path):
    d = tmp_path / "dataset"
    d.mkdir()
    (d / "manifest.json").write_text("{}")
    (d / "queries.json").write_text(
        json.dumps({"queries": [{"id": "q001", "type": "factual",
                                 "text": "test", "relevant_files": ["a.md"],
                                 "expected_answer_keywords": ["test"]}]})
    )
    for sub in ("knowledge", "episodes", "procedures", "noise"):
        (d / sub).mkdir()
    return d


@pytest.fixture
def output_dir(tmp_path):
    d = tmp_path / "output"
    d.mkdir()
    return d


# ── Result normalization tests ──────────────────────────────────


class TestResultNormalization:
    def test_normalize_priming_result_from_dict(self):
        from experiments.memory_eval.run_all import _normalize_priming_result
        raw = {
            "avg_priming_precision_at_3": 0.7,
            "avg_priming_precision_at_5": 0.6,
            "avg_priming_recall_at_5": 0.8,
            "avg_priming_tokens": 300,
            "avg_baseline_precision_at_3": 0.5,
            "avg_baseline_precision_at_5": 0.4,
            "avg_baseline_recall_at_5": 0.55,
            "n_queries": 20,
        }
        result = _normalize_priming_result(raw)
        assert result["on"]["precision_at_3"] == 0.7
        assert result["off"]["precision_at_3"] == 0.5
        assert result["n_queries"] == 20

    def test_normalize_forgetting_result_from_dict(self):
        from experiments.memory_eval.run_all import _normalize_forgetting_result
        raw = {
            "forgetting_precision_at_3": 0.65,
            "forgetting_precision_at_5": 0.55,
            "forgetting_recall_at_5": 0.7,
            "baseline_precision_at_3": 0.45,
            "baseline_precision_at_5": 0.35,
            "baseline_recall_at_5": 0.5,
            "total_before_forgetting": 130,
            "total_after_forgetting": 85,
        }
        result = _normalize_forgetting_result(raw)
        assert result["on"]["memory_count_before"] == 130
        assert result["on"]["memory_count_after"] == 85
        assert result["off"]["memory_count_after"] == 130

    def test_normalize_reconsolidation_result_from_dict(self):
        from experiments.memory_eval.run_all import (
            _normalize_reconsolidation_result,
        )
        raw = {
            "avg_round1_success_rate": 0.2,
            "avg_round2_success_rate_on": 0.85,
            "avg_round2_success_rate_off": 0.2,
            "n_procedures": 3,
        }
        result = _normalize_reconsolidation_result(raw)
        assert result["on"]["rounds"][0]["success_rate"] == 0.2
        assert result["on"]["rounds"][1]["success_rate"] == 0.85
        assert result["off"]["rounds"][1]["success_rate"] == 0.2
        assert result["n_procedures"] == 3


# ── Empty result factory tests ──────────────────────────────────


class TestEmptyResultFactories:
    def test_empty_priming_results(self):
        from experiments.memory_eval.run_all import _empty_priming_results
        result = _empty_priming_results()
        assert "on" in result and "off" in result
        assert result["on"]["precision_at_3"] == 0.0

    def test_empty_forgetting_results(self):
        from experiments.memory_eval.run_all import _empty_forgetting_results
        result = _empty_forgetting_results()
        assert result["on"]["memory_count_before"] == 0

    def test_empty_reconsolidation_results(self):
        from experiments.memory_eval.run_all import (
            _empty_reconsolidation_results,
        )
        result = _empty_reconsolidation_results()
        assert len(result["on"]["rounds"]) == 2
        assert result["on"]["overall_success_rate"] == 0.0


# ── run_dataset_generation tests ────────────────────────────────


class TestRunDatasetGeneration:
    @pytest.mark.asyncio
    async def test_skips_if_manifest_exists(self, tmp_path):
        from experiments.memory_eval.run_all import run_dataset_generation
        ds_dir = tmp_path / "dataset"
        ds_dir.mkdir()
        (ds_dir / "manifest.json").write_text("{}")
        result = await run_dataset_generation(tmp_path)
        assert result == ds_dir

    @pytest.mark.asyncio
    async def test_generates_dataset(self, tmp_path):
        mock_gen = MagicMock()
        mock_cls = MagicMock(return_value=mock_gen)
        with patch(
            "experiments.memory_eval.dataset.AblationDatasetGenerator",
            mock_cls,
        ):
            from experiments.memory_eval.run_all import run_dataset_generation
            result = await run_dataset_generation(tmp_path)
        assert result == tmp_path / "dataset"
        mock_gen.generate_all.assert_called_once()


# ── run_priming_ablation tests ──────────────────────────────────


class TestRunPrimingAblation:
    @pytest.mark.asyncio
    async def test_calls_priming_ablation(self, dataset_dir, output_dir):
        mock_ablation = MagicMock()
        mock_ablation.setup = AsyncMock()
        mock_ablation.run = AsyncMock(return_value=MagicMock())

        with patch(
            "experiments.memory_eval.ablation.priming.PrimingAblation",
            return_value=mock_ablation,
        ):
            from experiments.memory_eval.run_all import run_priming_ablation
            await run_priming_ablation(
                dataset_dir, output_dir, use_mock=True)
        mock_ablation.setup.assert_called_once()
        mock_ablation.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_saves_results_json(self, dataset_dir, output_dir):
        mock_ablation = MagicMock()
        mock_ablation.setup = AsyncMock()
        mock_ablation.run = AsyncMock(return_value=MagicMock())

        with patch(
            "experiments.memory_eval.ablation.priming.PrimingAblation",
            return_value=mock_ablation,
        ):
            from experiments.memory_eval.run_all import run_priming_ablation
            await run_priming_ablation(
                dataset_dir, output_dir, use_mock=True)
        assert (output_dir / "priming_results.json").exists()

    @pytest.mark.asyncio
    async def test_handles_exception(self, dataset_dir, output_dir):
        with patch(
            "experiments.memory_eval.ablation.priming.PrimingAblation",
            side_effect=RuntimeError("test"),
        ):
            from experiments.memory_eval.run_all import run_priming_ablation
            result = await run_priming_ablation(
                dataset_dir, output_dir, use_mock=True)
        assert result["on"]["precision_at_3"] == 0.0


# ── run_forgetting_ablation tests ───────────────────────────────


class TestRunForgettingAblation:
    @pytest.mark.asyncio
    async def test_calls_forgetting_ablation(self, dataset_dir, output_dir):
        mock_ablation = MagicMock()
        mock_ablation.run = MagicMock(return_value=MagicMock())

        with patch(
            "experiments.memory_eval.ablation.forgetting.ForgettingAblation",
            return_value=mock_ablation,
        ):
            from experiments.memory_eval.run_all import run_forgetting_ablation
            await run_forgetting_ablation(
                dataset_dir, output_dir, use_mock=True)
        mock_ablation.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_exception(self, dataset_dir, output_dir):
        with patch(
            "experiments.memory_eval.ablation.forgetting.ForgettingAblation",
            side_effect=RuntimeError("test"),
        ):
            from experiments.memory_eval.run_all import run_forgetting_ablation
            result = await run_forgetting_ablation(
                dataset_dir, output_dir, use_mock=True)
        assert result["on"]["precision_at_3"] == 0.0


# ── run_reconsolidation_ablation tests ──────────────────────────


class TestRunReconsolidationAblation:
    @pytest.mark.asyncio
    async def test_calls_reconsolidation_ablation(
        self, dataset_dir, output_dir,
    ):
        mock_ablation = MagicMock()
        mock_ablation.run = AsyncMock(return_value=MagicMock())

        with patch(
            "experiments.memory_eval.ablation.reconsolidation"
            ".ReconsolidationAblation",
            return_value=mock_ablation,
        ):
            from experiments.memory_eval.run_all import (
                run_reconsolidation_ablation,
            )
            await run_reconsolidation_ablation(
                dataset_dir, output_dir, use_mock=True)
        mock_ablation.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_exception(self, dataset_dir, output_dir):
        with patch(
            "experiments.memory_eval.ablation.reconsolidation"
            ".ReconsolidationAblation",
            side_effect=RuntimeError("test"),
        ):
            from experiments.memory_eval.run_all import (
                run_reconsolidation_ablation,
            )
            result = await run_reconsolidation_ablation(
                dataset_dir, output_dir, use_mock=True)
        assert result["on"]["overall_success_rate"] == 0.0


# ── run_all orchestration tests ─────────────────────────────────


class TestRunAll:
    @pytest.mark.asyncio
    async def test_saves_metadata(self, tmp_path, dataset_dir):
        """Should save meta.json with run configuration."""
        output_dir = tmp_path / "output"

        # Mock the three ablation runners at module level
        from experiments.memory_eval import run_all as ra

        orig_priming = ra.run_priming_ablation
        orig_forget = ra.run_forgetting_ablation
        orig_recon = ra.run_reconsolidation_ablation

        ra.run_priming_ablation = AsyncMock(return_value={"on": {}, "off": {}})
        ra.run_forgetting_ablation = AsyncMock(
            return_value={"on": {}, "off": {}})
        ra.run_reconsolidation_ablation = AsyncMock(
            return_value={"on": {"rounds": []}, "off": {"rounds": []}})

        try:
            with patch(
                "experiments.memory_eval.analysis.visualize"
                ".generate_all_figures",
                return_value=[],
            ), patch(
                "experiments.memory_eval.analysis.report.generate_report",
            ):
                await ra.run_all(
                    output_dir=output_dir,
                    dataset_dir=dataset_dir,
                    use_mock=True,
                )
        finally:
            ra.run_priming_ablation = orig_priming
            ra.run_forgetting_ablation = orig_forget
            ra.run_reconsolidation_ablation = orig_recon

        meta_path = output_dir / "meta.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["mode"] == "mock"


# ── CLI main() tests ────────────────────────────────────────────


class TestMainCLI:
    def test_main_parses_args(self):
        with patch("sys.argv", ["run_all.py"]), \
             patch("experiments.memory_eval.run_all.asyncio.run") as mock_run:
            from experiments.memory_eval.run_all import main
            main()
            mock_run.assert_called_once()

    def test_main_verbose_flag(self):
        with patch("sys.argv", ["run_all.py", "--verbose"]), \
             patch("experiments.memory_eval.run_all.asyncio.run"), \
             patch("experiments.memory_eval.run_all.logging.basicConfig") as ml:
            from experiments.memory_eval.run_all import main
            main()
            import logging
            assert ml.call_args[1]["level"] == logging.DEBUG

    def test_main_ablation_arg(self):
        with patch("sys.argv", ["run_all.py", "--ablation", "priming"]), \
             patch("experiments.memory_eval.run_all.asyncio.run") as mock_run:
            from experiments.memory_eval.run_all import main
            main()
            mock_run.assert_called_once()

    def test_main_live_flag(self):
        with patch("sys.argv", ["run_all.py", "--live"]), \
             patch("experiments.memory_eval.run_all.asyncio.run") as mock_run:
            from experiments.memory_eval.run_all import main
            main()
            mock_run.assert_called_once()
