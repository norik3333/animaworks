from __future__ import annotations

"""Unit tests for visualization module.

Uses mocked matplotlib to verify correct figure generation without
requiring matplotlib to be installed.
"""

import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


# ── Mock numpy array ─────────────────────────────────────────────


class _MockArray(list):
    """List subclass that supports basic numpy-style arithmetic."""

    def __sub__(self, other):
        return _MockArray([v - other for v in self])

    def __rsub__(self, other):
        return _MockArray([other - v for v in self])

    def __add__(self, other):
        if isinstance(other, (int, float)):
            return _MockArray([v + other for v in self])
        return _MockArray(list.__add__(self, other))

    def __radd__(self, other):
        if isinstance(other, (int, float)):
            return _MockArray([other + v for v in self])
        return NotImplemented

    def __mul__(self, other):
        if isinstance(other, (int, float)):
            return _MockArray([v * other for v in self])
        return NotImplemented

    def __truediv__(self, other):
        return _MockArray([v / other for v in self])


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def sample_priming_results():
    return {
        "on": {"precision_at_3": 0.70, "precision_at_5": 0.60,
               "recall_at_5": 0.75, "avg_priming_tokens": 300},
        "off": {"precision_at_3": 0.50, "precision_at_5": 0.40,
                "recall_at_5": 0.55},
    }


@pytest.fixture
def sample_forgetting_results():
    return {
        "on": {"precision_at_3": 0.65, "precision_at_5": 0.55,
               "memory_count_before": 130, "memory_count_after": 85},
        "off": {"precision_at_3": 0.45, "precision_at_5": 0.35,
                "memory_count_before": 130, "memory_count_after": 130},
    }


@pytest.fixture
def sample_reconsolidation_results():
    return {
        "on": {"rounds": [{"success_rate": 0.2}, {"success_rate": 0.8}],
               "overall_success_rate": 0.8},
        "off": {"rounds": [{"success_rate": 0.2}, {"success_rate": 0.2}],
                "overall_success_rate": 0.2},
    }


@pytest.fixture
def results_dir(tmp_path, sample_priming_results,
                sample_forgetting_results, sample_reconsolidation_results):
    d = tmp_path / "results"
    d.mkdir()
    (d / "priming_results.json").write_text(json.dumps(sample_priming_results))
    (d / "forgetting_results.json").write_text(
        json.dumps(sample_forgetting_results))
    (d / "reconsolidation_results.json").write_text(
        json.dumps(sample_reconsolidation_results))
    return d


def _make_mock_plt():
    """Build a mock matplotlib.pyplot with intelligent subplots routing."""
    mock_plt = MagicMock()
    mock_fig = MagicMock()

    def _subplots_side_effect(*args, **kwargs):
        """Return appropriate axis shapes depending on call signature."""
        nrows = args[0] if len(args) > 0 else kwargs.get("nrows", 1)
        ncols = args[1] if len(args) > 1 else kwargs.get("ncols", 1)
        if nrows == 1 and ncols == 1:
            return (mock_fig, MagicMock())
        if nrows == 1 and ncols == 2:
            return (mock_fig, (MagicMock(), MagicMock()))
        if nrows == 2 and ncols == 2:
            # Return a 2D-indexable mock (axes[row, col])
            cells = [[MagicMock() for _ in range(ncols)] for _ in range(nrows)]
            axes_mock = MagicMock()
            axes_mock.__getitem__ = lambda self, key: cells[key[0]][key[1]]
            axes_mock.flat = [c for row in cells for c in row]
            return (mock_fig, axes_mock)
        return (mock_fig, MagicMock())

    mock_plt.subplots.side_effect = _subplots_side_effect
    return mock_plt, mock_fig


def _make_mock_np():
    """Build a mock numpy with arange returning arithmetic-capable arrays."""
    mock_np = MagicMock()
    mock_np.arange.side_effect = lambda n: _MockArray(range(n))
    return mock_np


@pytest.fixture
def viz_module():
    """Import visualize module with matplotlib and numpy mocked."""
    mock_mpl = MagicMock()
    mock_plt, mock_fig = _make_mock_plt()
    mock_np = _make_mock_np()

    # Inject mocks into sys.modules before importing
    saved = {}
    for mod_name in ("matplotlib", "matplotlib.pyplot", "numpy"):
        saved[mod_name] = sys.modules.get(mod_name)

    sys.modules["matplotlib"] = mock_mpl
    sys.modules["matplotlib.pyplot"] = mock_plt
    sys.modules["numpy"] = mock_np

    # Force reimport
    mod_key = "experiments.memory_eval.analysis.visualize"
    if mod_key in sys.modules:
        del sys.modules[mod_key]

    import experiments.memory_eval.analysis.visualize as viz
    viz._setup_matplotlib = MagicMock(return_value=mock_plt)

    yield viz, mock_plt, mock_fig, mock_np

    # Restore
    for mod_name, orig in saved.items():
        if orig is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = orig
    sys.modules.pop(mod_key, None)


# ── Module import tests ─────────────────────────────────────────


class TestModuleImport:
    def test_module_imports(self):
        from experiments.memory_eval.analysis import visualize
        assert hasattr(visualize, "generate_all_figures")
        assert hasattr(visualize, "plot_priming_comparison")

    def test_constants_defined(self):
        from experiments.memory_eval.analysis.visualize import (
            COLOR_ON, COLOR_OFF, DPI, FIG_SIZE_SINGLE, FIG_SIZE_DASHBOARD,
        )
        assert isinstance(COLOR_ON, str)
        assert isinstance(COLOR_OFF, str)
        assert DPI == 300
        assert len(FIG_SIZE_SINGLE) == 2
        assert len(FIG_SIZE_DASHBOARD) == 2


# ── _save_figure tests ──────────────────────────────────────────


class TestSaveFigure:
    def test_creates_output_directory(self, tmp_path):
        from experiments.memory_eval.analysis.visualize import _save_figure
        output_dir = tmp_path / "nested" / "dir"
        mock_fig = MagicMock()
        paths = _save_figure(mock_fig, output_dir, "test_fig")
        assert output_dir.exists()
        assert len(paths) == 2
        assert paths[0].suffix == ".png"
        assert paths[1].suffix == ".pdf"

    def test_calls_savefig(self, tmp_path):
        from experiments.memory_eval.analysis.visualize import _save_figure
        mock_fig = MagicMock()
        _save_figure(mock_fig, tmp_path, "test_fig")
        assert mock_fig.savefig.call_count == 2
        calls = mock_fig.savefig.call_args_list
        assert calls[0][1]["format"] == "png"
        assert calls[1][1]["format"] == "pdf"

    def test_output_paths(self, tmp_path):
        from experiments.memory_eval.analysis.visualize import _save_figure
        mock_fig = MagicMock()
        paths = _save_figure(mock_fig, tmp_path, "my_chart")
        assert paths[0] == tmp_path / "my_chart.png"
        assert paths[1] == tmp_path / "my_chart.pdf"


# ── generate_all_figures tests ──────────────────────────────────


class TestGenerateAllFigures:
    def test_missing_all_result_files(self, viz_module, tmp_path):
        viz, *_ = viz_module
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        result = viz.generate_all_figures(empty_dir, tmp_path / "output")
        assert result == []

    def test_reads_correct_files(self, viz_module, results_dir, tmp_path):
        viz, mock_plt, mock_fig, _ = viz_module
        output_dir = tmp_path / "figures"
        result = viz.generate_all_figures(results_dir, output_dir)
        # 4 figures: priming, forgetting, reconsolidation, dashboard
        assert len(result) == 4

    def test_partial_results(self, viz_module, tmp_path,
                             sample_priming_results):
        viz, *_ = viz_module
        results_dir = tmp_path / "partial"
        results_dir.mkdir()
        (results_dir / "priming_results.json").write_text(
            json.dumps(sample_priming_results))
        result = viz.generate_all_figures(results_dir, tmp_path / "figures")
        # With only priming: priming plot + dashboard (partial)
        assert len(result) >= 1


# ── plot_priming_comparison tests ───────────────────────────────


class TestPlotPrimingComparison:
    def test_handles_empty_results(self, viz_module, tmp_path):
        viz, mock_plt, mock_fig, _ = viz_module
        result = viz.plot_priming_comparison({}, tmp_path)
        mock_plt.close.assert_called_with(mock_fig)

    def test_extracts_correct_metrics(self, viz_module, tmp_path,
                                      sample_priming_results):
        viz, mock_plt, mock_fig, _ = viz_module
        result = viz.plot_priming_comparison(sample_priming_results, tmp_path)
        # Should have generated a figure (returned a path)
        assert result is not None


# ── plot_forgetting_comparison tests ────────────────────────────


class TestPlotForgettingComparison:
    def test_handles_empty_results(self, viz_module, tmp_path):
        viz, mock_plt, mock_fig, _ = viz_module
        result = viz.plot_forgetting_comparison({}, tmp_path)
        mock_plt.close.assert_called_with(mock_fig)

    def test_with_data(self, viz_module, tmp_path,
                       sample_forgetting_results):
        viz, mock_plt, mock_fig, _ = viz_module
        result = viz.plot_forgetting_comparison(
            sample_forgetting_results, tmp_path)
        assert result is not None


# ── plot_reconsolidation_progression tests ──────────────────────


class TestPlotReconsolidationProgression:
    def test_handles_empty_rounds(self, viz_module, tmp_path):
        viz, mock_plt, mock_fig, _ = viz_module
        result = viz.plot_reconsolidation_progression(
            {"on": {"rounds": []}, "off": {"rounds": []}}, tmp_path)
        mock_plt.close.assert_called_with(mock_fig)

    def test_with_round_data(self, viz_module, tmp_path,
                             sample_reconsolidation_results):
        viz, mock_plt, mock_fig, _ = viz_module
        result = viz.plot_reconsolidation_progression(
            sample_reconsolidation_results, tmp_path)
        assert result is not None


# ── plot_summary_dashboard tests ────────────────────────────────


class TestPlotSummaryDashboard:
    def test_creates_2x2_grid(self, viz_module, tmp_path,
                              sample_priming_results,
                              sample_forgetting_results,
                              sample_reconsolidation_results):
        viz, mock_plt, mock_fig, _ = viz_module
        result = viz.plot_summary_dashboard(
            sample_priming_results, sample_forgetting_results,
            sample_reconsolidation_results, tmp_path)
        assert result is not None

    def test_with_empty_results(self, viz_module, tmp_path):
        viz, mock_plt, mock_fig, _ = viz_module
        result = viz.plot_summary_dashboard({}, {}, {}, tmp_path)
        mock_plt.close.assert_called_with(mock_fig)
