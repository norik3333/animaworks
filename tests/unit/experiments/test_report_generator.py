from __future__ import annotations

"""Unit tests for report generator."""

import json

import pytest

from experiments.memory_eval.analysis.report import generate_report


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def results_dir(tmp_path):
    """Create a results directory with sample JSON result files."""
    rd = tmp_path / "results"
    rd.mkdir()

    # Priming results
    priming = {
        "on": {
            "precision_at_3": 0.75,
            "precision_at_5": 0.65,
            "recall_at_5": 0.80,
            "avg_priming_tokens": 350,
        },
        "off": {
            "precision_at_3": 0.55,
            "precision_at_5": 0.45,
            "recall_at_5": 0.60,
        },
        "n_queries": 20,
    }
    (rd / "priming_results.json").write_text(
        json.dumps(priming, indent=2), encoding="utf-8",
    )

    # Forgetting results
    forgetting = {
        "on": {
            "precision_at_3": 0.70,
            "precision_at_5": 0.60,
            "recall_at_5": 0.75,
            "memory_count_before": 130,
            "memory_count_after": 80,
        },
        "off": {
            "precision_at_3": 0.50,
            "precision_at_5": 0.40,
            "recall_at_5": 0.55,
            "memory_count_before": 130,
            "memory_count_after": 130,
        },
        "n_queries": 20,
    }
    (rd / "forgetting_results.json").write_text(
        json.dumps(forgetting, indent=2), encoding="utf-8",
    )

    # Reconsolidation results
    reconsolidation = {
        "on": {
            "rounds": [
                {"success_rate": 0.20},
                {"success_rate": 0.85},
            ],
            "overall_success_rate": 0.85,
        },
        "off": {
            "rounds": [
                {"success_rate": 0.20},
                {"success_rate": 0.25},
            ],
            "overall_success_rate": 0.25,
        },
        "n_procedures": 5,
    }
    (rd / "reconsolidation_results.json").write_text(
        json.dumps(reconsolidation, indent=2), encoding="utf-8",
    )

    return rd


# ── Tests ────────────────────────────────────────────────────────


class TestGenerateReport:
    """Tests for report generation."""

    def test_creates_output_file(self, results_dir, tmp_path):
        """Should create a Markdown report file."""
        output_path = tmp_path / "report.md"
        result = generate_report(results_dir, output_path)

        assert result == output_path
        assert output_path.exists()

    def test_contains_priming_section(self, results_dir, tmp_path):
        """Report should contain priming ablation results."""
        output_path = tmp_path / "report.md"
        generate_report(results_dir, output_path)
        content = output_path.read_text(encoding="utf-8")

        assert "Priming" in content or "priming" in content

    def test_contains_forgetting_section(self, results_dir, tmp_path):
        """Report should contain forgetting ablation results."""
        output_path = tmp_path / "report.md"
        generate_report(results_dir, output_path)
        content = output_path.read_text(encoding="utf-8")

        assert "Forgetting" in content or "forgetting" in content

    def test_contains_reconsolidation_section(self, results_dir, tmp_path):
        """Report should contain reconsolidation ablation results."""
        output_path = tmp_path / "report.md"
        generate_report(results_dir, output_path)
        content = output_path.read_text(encoding="utf-8")

        assert "Reconsolidation" in content or "reconsolidation" in content

    def test_contains_tables(self, results_dir, tmp_path):
        """Report should contain Markdown tables with metric values."""
        output_path = tmp_path / "report.md"
        generate_report(results_dir, output_path)
        content = output_path.read_text(encoding="utf-8")

        # Markdown table indicators
        assert "|" in content
        assert "---" in content or ":-" in content

    def test_contains_numeric_values(self, results_dir, tmp_path):
        """Report should include actual metric values from results."""
        output_path = tmp_path / "report.md"
        generate_report(results_dir, output_path)
        content = output_path.read_text(encoding="utf-8")

        # Should contain some of our input values
        assert "0.75" in content or "0.55" in content or "0.65" in content

    def test_handles_missing_results(self, tmp_path):
        """Should handle partially missing result files gracefully."""
        results_dir = tmp_path / "sparse"
        results_dir.mkdir()

        # Only create priming results
        priming = {
            "on": {"precision_at_3": 0.5, "precision_at_5": 0.4, "recall_at_5": 0.6},
            "off": {"precision_at_3": 0.3, "precision_at_5": 0.2, "recall_at_5": 0.3},
        }
        (results_dir / "priming_results.json").write_text(
            json.dumps(priming), encoding="utf-8",
        )

        output_path = tmp_path / "report.md"
        generate_report(results_dir, output_path)

        assert output_path.exists()
        content = output_path.read_text(encoding="utf-8")
        assert len(content) > 50

    def test_handles_empty_results_dir(self, tmp_path):
        """Should handle empty results directory gracefully."""
        results_dir = tmp_path / "empty"
        results_dir.mkdir()

        output_path = tmp_path / "report.md"
        generate_report(results_dir, output_path)

        assert output_path.exists()

    def test_creates_parent_dirs(self, results_dir, tmp_path):
        """Should create parent directories for output path."""
        output_path = tmp_path / "nested" / "dir" / "report.md"
        generate_report(results_dir, output_path)

        assert output_path.exists()
