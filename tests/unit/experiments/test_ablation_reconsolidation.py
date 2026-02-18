from __future__ import annotations

"""Unit tests for Reconsolidation ON/OFF ablation experiment."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from experiments.memory_eval.ablation.reconsolidation import (
    ProcedureResult,
    ReconsolidationAblation,
    ReconsolidationAblationResult,
)


# ── Fixtures ─────────────────────────────────────────────────────


def _write_procedure(path: Path, *, flawed: bool = True, confidence: float = 0.5) -> None:
    """Write a procedure file with optional flaw markers."""
    meta = {
        "description": "Test procedure",
        "success_count": 0,
        "failure_count": 0,
        "confidence": confidence,
        "version": 1,
        "created_at": "2026-01-01T00:00:00",
        "last_used": None,
    }
    fm = yaml.dump(meta, default_flow_style=False, allow_unicode=True).rstrip()
    body = "# Test Procedure\n\n"
    if flawed:
        body += "Step 1: TODO - this step is incomplete\nStep 2: placeholder\n"
    else:
        body += "Step 1: Complete the task correctly\nStep 2: Verify results\n"
    path.write_text(f"---\n{fm}\n---\n\n{body}", encoding="utf-8")


@pytest.fixture
def dataset_dir(tmp_path):
    """Create a minimal dataset with flawed procedures."""
    ds = tmp_path / "dataset"

    # Flawed procedures
    flawed_dir = ds / "flawed_procedures"
    flawed_dir.mkdir(parents=True)
    _write_procedure(flawed_dir / "proc_a.md", flawed=True)
    _write_procedure(flawed_dir / "proc_b.md", flawed=True)

    # Fixed procedures (for mock mode)
    fixed_dir = ds / "fixed_procedures"
    fixed_dir.mkdir(parents=True)
    _write_procedure(fixed_dir / "proc_a.md", flawed=False)
    _write_procedure(fixed_dir / "proc_b.md", flawed=False)

    return ds


@pytest.fixture
def output_dir(tmp_path):
    """Output directory for results."""
    out = tmp_path / "output"
    out.mkdir()
    return out


# ── Data structure tests ─────────────────────────────────────────


class TestProcedureResult:
    """Tests for ProcedureResult dataclass."""

    def test_defaults(self):
        """Default values should be zeros."""
        r = ProcedureResult(name="test")
        assert r.initial_confidence == 0.0
        assert r.round1_successes == 0
        assert r.round1_failures == 0
        assert r.was_reconsolidated is False
        assert r.success_rate_delta == 0.0


class TestReconsolidationAblationResult:
    """Tests for ReconsolidationAblationResult dataclass."""

    def test_defaults(self):
        """Default aggregates should be zero."""
        r = ReconsolidationAblationResult()
        assert r.n_procedures == 0
        assert r.avg_round1_success_rate == 0.0
        assert r.on_results == []
        assert r.off_results == []


# ── Frontmatter helpers ──────────────────────────────────────────


class TestFrontmatterHelpers:
    """Tests for YAML frontmatter parsing and writing."""

    def test_strip_frontmatter(self):
        """Should strip YAML frontmatter and return body."""
        content = "---\nkey: value\n---\n\nBody text here"
        body = ReconsolidationAblation._strip_frontmatter(content)
        assert body == "Body text here"

    def test_strip_frontmatter_no_frontmatter(self):
        """Should return content as-is if no frontmatter."""
        content = "No frontmatter here"
        body = ReconsolidationAblation._strip_frontmatter(content)
        assert body == "No frontmatter here"

    def test_parse_frontmatter(self):
        """Should parse YAML frontmatter into dict."""
        content = "---\nconfidence: 0.8\nversion: 2\n---\n\nBody"
        meta = ReconsolidationAblation._parse_frontmatter(content)
        assert meta["confidence"] == 0.8
        assert meta["version"] == 2

    def test_parse_frontmatter_empty(self):
        """Should return empty dict for no frontmatter."""
        meta = ReconsolidationAblation._parse_frontmatter("No frontmatter")
        assert meta == {}

    def test_write_with_frontmatter(self, tmp_path):
        """Should write file with proper YAML frontmatter."""
        path = tmp_path / "test.md"
        meta = {"confidence": 0.9, "version": 3}
        body = "# Procedure\nStep 1: Do thing"

        ReconsolidationAblation._write_with_frontmatter(path, body, meta)

        content = path.read_text(encoding="utf-8")
        assert content.startswith("---\n")
        parsed_meta = ReconsolidationAblation._parse_frontmatter(content)
        assert parsed_meta["confidence"] == 0.9
        parsed_body = ReconsolidationAblation._strip_frontmatter(content)
        assert "Step 1: Do thing" in parsed_body


# ── Execution simulation ────────────────────────────────────────


class TestSimulateExecution:
    """Tests for procedure execution simulation."""

    def test_flawed_procedure_fails(self, tmp_path):
        """Flawed procedures should consistently fail."""
        path = tmp_path / "flawed.md"
        _write_procedure(path, flawed=True)

        ablation = ReconsolidationAblation(tmp_path, tmp_path / "out")
        result = ablation._simulate_execution(path, is_flawed=True)
        assert result is False

    def test_correct_procedure_succeeds(self, tmp_path):
        """Correct procedures should consistently succeed."""
        path = tmp_path / "correct.md"
        _write_procedure(path, flawed=False)

        ablation = ReconsolidationAblation(tmp_path, tmp_path / "out")
        result = ablation._simulate_execution(path, is_flawed=False)
        assert result is True


# ── Frontmatter update ───────────────────────────────────────────


class TestUpdateFrontmatter:
    """Tests for updating procedure frontmatter with trial results."""

    def test_success_increments_counter(self, tmp_path):
        """Success should increment success_count."""
        path = tmp_path / "proc.md"
        _write_procedure(path, flawed=False)

        ablation = ReconsolidationAblation(tmp_path, tmp_path / "out")
        meta = ablation._update_frontmatter(path, success=True)

        assert meta["success_count"] == 1
        assert meta["failure_count"] == 0
        assert meta["confidence"] == 1.0

    def test_failure_increments_counter(self, tmp_path):
        """Failure should increment failure_count."""
        path = tmp_path / "proc.md"
        _write_procedure(path, flawed=True)

        ablation = ReconsolidationAblation(tmp_path, tmp_path / "out")
        meta = ablation._update_frontmatter(path, success=False)

        assert meta["failure_count"] == 1
        assert meta["success_count"] == 0
        assert meta["confidence"] == 0.0

    def test_confidence_calculation(self, tmp_path):
        """Confidence should be success_count / total."""
        path = tmp_path / "proc.md"
        _write_procedure(path, flawed=True)

        ablation = ReconsolidationAblation(tmp_path, tmp_path / "out")
        # 2 successes, 1 failure
        ablation._update_frontmatter(path, success=True)
        ablation._update_frontmatter(path, success=True)
        meta = ablation._update_frontmatter(path, success=False)

        assert abs(meta["confidence"] - 2 / 3) < 0.01
        assert meta["success_count"] == 2
        assert meta["failure_count"] == 1

    def test_updates_last_used(self, tmp_path):
        """Should set last_used timestamp."""
        path = tmp_path / "proc.md"
        _write_procedure(path, flawed=False)

        ablation = ReconsolidationAblation(tmp_path, tmp_path / "out")
        meta = ablation._update_frontmatter(path, success=True)

        assert "last_used" in meta
        assert meta["last_used"] is not None


# ── Mock reconsolidation ─────────────────────────────────────────


class TestMockReconsolidate:
    """Tests for mock reconsolidation logic."""

    def test_mock_fix_removes_flaws(self, tmp_path):
        """Mock reconsolidation should remove flaw markers."""
        path = tmp_path / "proc.md"
        _write_procedure(path, flawed=True)

        ablation = ReconsolidationAblation(tmp_path, tmp_path / "out")
        ablation._mock_reconsolidate(path)

        content = path.read_text(encoding="utf-8")
        assert "todo" not in content.lower() or "placeholder" not in content.lower()
        meta = ReconsolidationAblation._parse_frontmatter(content)
        assert meta["version"] == 2
        assert meta["failure_count"] == 0
        assert meta["confidence"] == 0.5

    def test_mock_fix_from_fixed_procedures(self, dataset_dir, output_dir, tmp_path):
        """Should use predefined fix from fixed_procedures/ when available."""
        ablation = ReconsolidationAblation(dataset_dir, output_dir, use_mock=True)
        ablation._load_mock_fixes()

        # Copy a flawed procedure
        src = dataset_dir / "flawed_procedures" / "proc_a.md"
        dst = tmp_path / "proc_a.md"
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

        ablation._mock_reconsolidate(dst)

        content = dst.read_text(encoding="utf-8")
        body = ReconsolidationAblation._strip_frontmatter(content)
        # Should contain content from the fixed version
        assert "correctly" in body.lower() or "verify" in body.lower()

    def test_version_increments(self, tmp_path):
        """Reconsolidation should increment version."""
        path = tmp_path / "proc.md"
        _write_procedure(path, flawed=True)

        ablation = ReconsolidationAblation(tmp_path, tmp_path / "out")
        ablation._mock_reconsolidate(path)

        meta = ReconsolidationAblation._parse_frontmatter(
            path.read_text(encoding="utf-8"),
        )
        assert meta["version"] == 2

        ablation._mock_reconsolidate(path)
        meta = ReconsolidationAblation._parse_frontmatter(
            path.read_text(encoding="utf-8"),
        )
        assert meta["version"] == 3


# ── Run with reconsolidation ─────────────────────────────────────


class TestRunWithReconsolidation:
    """Tests for run_with_reconsolidation method."""

    @pytest.mark.asyncio
    async def test_returns_procedure_results(self, dataset_dir, output_dir, tmp_path):
        """Should return one result per procedure."""
        ablation = ReconsolidationAblation(dataset_dir, output_dir, use_mock=True)
        ablation._load_mock_fixes()

        work_dir = tmp_path / "work"
        work_dir.mkdir()
        results = await ablation.run_with_reconsolidation(work_dir)

        assert len(results) == 2  # proc_a and proc_b

    @pytest.mark.asyncio
    async def test_round1_failures_for_flawed(self, dataset_dir, output_dir, tmp_path):
        """Flawed procedures should fail in round 1."""
        ablation = ReconsolidationAblation(dataset_dir, output_dir, use_mock=True)
        ablation._load_mock_fixes()

        work_dir = tmp_path / "work"
        work_dir.mkdir()
        results = await ablation.run_with_reconsolidation(work_dir)

        for r in results:
            # Flawed procedures should fail consistently in round 1
            assert r.round1_failures > 0
            assert r.round1_success_rate < 1.0

    @pytest.mark.asyncio
    async def test_reconsolidation_triggers(self, dataset_dir, output_dir, tmp_path):
        """Reconsolidation should trigger for high-failure procedures."""
        ablation = ReconsolidationAblation(dataset_dir, output_dir, use_mock=True)
        ablation._load_mock_fixes()

        work_dir = tmp_path / "work"
        work_dir.mkdir()
        results = await ablation.run_with_reconsolidation(work_dir)

        # At least one procedure should be reconsolidated
        reconsolidated = [r for r in results if r.was_reconsolidated]
        assert len(reconsolidated) > 0

    @pytest.mark.asyncio
    async def test_round2_improves_after_reconsolidation(
        self, dataset_dir, output_dir, tmp_path,
    ):
        """Round 2 success rate should improve after reconsolidation."""
        ablation = ReconsolidationAblation(dataset_dir, output_dir, use_mock=True)
        ablation._load_mock_fixes()

        work_dir = tmp_path / "work"
        work_dir.mkdir()
        results = await ablation.run_with_reconsolidation(work_dir)

        for r in results:
            if r.was_reconsolidated:
                # After fixing, round 2 should be better than round 1
                assert r.round2_success_rate >= r.round1_success_rate


# ── Run without reconsolidation ──────────────────────────────────


class TestRunWithoutReconsolidation:
    """Tests for run_without_reconsolidation method."""

    @pytest.mark.asyncio
    async def test_no_reconsolidation_flag(self, dataset_dir, output_dir, tmp_path):
        """No procedure should be marked as reconsolidated."""
        ablation = ReconsolidationAblation(dataset_dir, output_dir, use_mock=True)

        work_dir = tmp_path / "work"
        work_dir.mkdir()
        results = await ablation.run_without_reconsolidation(work_dir)

        for r in results:
            assert r.was_reconsolidated is False

    @pytest.mark.asyncio
    async def test_flawed_stays_flawed(self, dataset_dir, output_dir, tmp_path):
        """Without reconsolidation, flawed procedures stay flawed in round 2."""
        ablation = ReconsolidationAblation(dataset_dir, output_dir, use_mock=True)

        work_dir = tmp_path / "work"
        work_dir.mkdir()
        results = await ablation.run_without_reconsolidation(work_dir)

        for r in results:
            # Round 2 should not improve without reconsolidation
            assert r.round2_success_rate <= r.round1_success_rate or (
                r.round1_success_rate == 0.0 and r.round2_success_rate == 0.0
            )


# ── Full run test ────────────────────────────────────────────────


class TestFullRun:
    """Tests for the complete ablation run."""

    @pytest.mark.asyncio
    async def test_run_saves_json(self, dataset_dir, output_dir, tmp_path):
        """run() should save results to output directory."""
        ablation = ReconsolidationAblation(dataset_dir, output_dir, use_mock=True)

        work_dir = tmp_path / "work"
        work_dir.mkdir()
        result = await ablation.run(work_dir)

        assert isinstance(result, ReconsolidationAblationResult)
        assert result.n_procedures == 2
        assert result.use_mock is True
        assert result.timestamp != ""

        # Check output file
        output_file = output_dir / "reconsolidation_ablation_result.json"
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert data["n_procedures"] == 2

    @pytest.mark.asyncio
    async def test_on_improves_vs_off(self, dataset_dir, output_dir, tmp_path):
        """ON condition should show improvement, OFF should not."""
        ablation = ReconsolidationAblation(dataset_dir, output_dir, use_mock=True)

        work_dir = tmp_path / "work"
        work_dir.mkdir()
        result = await ablation.run(work_dir)

        # ON (with reconsolidation) should improve
        assert result.avg_improvement_on >= result.avg_improvement_off

    @pytest.mark.asyncio
    async def test_success_rate_calculation(self, dataset_dir, output_dir, tmp_path):
        """Success rates should be valid fractions (0.0 to 1.0)."""
        ablation = ReconsolidationAblation(dataset_dir, output_dir, use_mock=True)

        work_dir = tmp_path / "work"
        work_dir.mkdir()
        result = await ablation.run(work_dir)

        assert 0.0 <= result.avg_round1_success_rate <= 1.0
        assert 0.0 <= result.avg_round2_success_rate_on <= 1.0
        assert 0.0 <= result.avg_round2_success_rate_off <= 1.0


# ── Load flawed procedures ───────────────────────────────────────


class TestLoadFlawedProcedures:
    """Tests for loading flawed procedures from dataset."""

    def test_loads_from_flawed_procedures_dir(self, dataset_dir, tmp_path):
        """Should copy from flawed_procedures/ directory."""
        ablation = ReconsolidationAblation(dataset_dir, tmp_path / "out")
        proc_dir = tmp_path / "procedures"

        files = ablation._load_flawed_procedures(proc_dir)

        assert len(files) == 2
        assert all(f.exists() for f in files)

    def test_handles_missing_directory(self, tmp_path):
        """Should handle missing source directory gracefully."""
        empty_ds = tmp_path / "empty"
        empty_ds.mkdir()

        ablation = ReconsolidationAblation(empty_ds, tmp_path / "out")
        proc_dir = tmp_path / "procedures"

        files = ablation._load_flawed_procedures(proc_dir)
        assert files == []
