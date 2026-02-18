from __future__ import annotations

"""Unit tests for AblationDatasetGenerator."""

import json

import pytest
import yaml

from experiments.memory_eval.dataset.generator import AblationDatasetGenerator


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def dataset_dir(tmp_path):
    """Generate a complete dataset and return its directory."""
    gen = AblationDatasetGenerator(output_dir=tmp_path, seed=42)
    gen.generate_all()
    return tmp_path


@pytest.fixture
def generator(tmp_path):
    """Return a fresh generator instance."""
    return AblationDatasetGenerator(output_dir=tmp_path, seed=42)


# ── Knowledge files ──────────────────────────────────────────────


class TestKnowledgeGeneration:
    """Tests for knowledge file generation."""

    def test_correct_file_count(self, dataset_dir):
        """30 knowledge files should be generated."""
        knowledge_dir = dataset_dir / "knowledge"
        files = list(knowledge_dir.glob("*.md"))
        assert len(files) == 30

    def test_yaml_frontmatter_present(self, dataset_dir):
        """Each knowledge file should have valid YAML frontmatter."""
        knowledge_dir = dataset_dir / "knowledge"
        for f in knowledge_dir.glob("*.md"):
            content = f.read_text(encoding="utf-8")
            assert content.startswith("---"), f"{f.name} missing frontmatter"
            parts = content.split("---", 2)
            assert len(parts) >= 3, f"{f.name} invalid frontmatter"
            meta = yaml.safe_load(parts[1])
            assert isinstance(meta, dict), f"{f.name} frontmatter not a dict"

    def test_frontmatter_fields(self, dataset_dir):
        """Frontmatter should contain expected fields."""
        knowledge_dir = dataset_dir / "knowledge"
        first_file = next(knowledge_dir.glob("*.md"))
        content = first_file.read_text(encoding="utf-8")
        parts = content.split("---", 2)
        meta = yaml.safe_load(parts[1])

        expected_fields = {"created_at", "updated_at", "confidence", "version"}
        assert expected_fields.issubset(set(meta.keys())), (
            f"Missing fields: {expected_fields - set(meta.keys())}"
        )

    def test_content_not_empty(self, dataset_dir):
        """Knowledge file bodies should be non-empty."""
        knowledge_dir = dataset_dir / "knowledge"
        for f in knowledge_dir.glob("*.md"):
            content = f.read_text(encoding="utf-8")
            parts = content.split("---", 2)
            body = parts[2].strip() if len(parts) >= 3 else content.strip()
            assert len(body) > 50, f"{f.name} body too short"


# ── Episode files ────────────────────────────────────────────────


class TestEpisodeGeneration:
    """Tests for episode file generation."""

    def test_correct_file_count(self, dataset_dir):
        """15 episode files should be generated."""
        episodes_dir = dataset_dir / "episodes"
        files = list(episodes_dir.glob("*.md"))
        assert len(files) == 15

    def test_date_format(self, dataset_dir):
        """Episode files should be named with YYYY-MM-DD.md format."""
        episodes_dir = dataset_dir / "episodes"
        for f in episodes_dir.glob("*.md"):
            stem = f.stem
            parts = stem.split("-")
            assert len(parts) == 3, f"{f.name} not in date format"
            year, month, day = parts
            assert len(year) == 4 and year.isdigit()
            assert len(month) == 2 and month.isdigit()
            assert len(day) == 2 and day.isdigit()


# ── Procedure files ──────────────────────────────────────────────


class TestProcedureGeneration:
    """Tests for procedure file generation."""

    def test_correct_file_count(self, dataset_dir):
        """5 procedure files should be generated."""
        procedures_dir = dataset_dir / "procedures"
        files = list(procedures_dir.glob("*.md"))
        assert len(files) == 5

    def test_procedure_frontmatter(self, dataset_dir):
        """Procedure files should have YAML frontmatter with expected fields."""
        procedures_dir = dataset_dir / "procedures"
        for f in procedures_dir.glob("*.md"):
            content = f.read_text(encoding="utf-8")
            assert content.startswith("---"), f"{f.name} missing frontmatter"
            parts = content.split("---", 2)
            meta = yaml.safe_load(parts[1])
            assert "description" in meta, f"{f.name} missing description"


# ── Skill files ──────────────────────────────────────────────────


class TestSkillGeneration:
    """Tests for skill file generation."""

    def test_correct_file_count(self, dataset_dir):
        """5 skill files should be generated."""
        skills_dir = dataset_dir / "skills"
        files = list(skills_dir.glob("*.md"))
        assert len(files) == 5


# ── Noise files ──────────────────────────────────────────────────


class TestNoiseGeneration:
    """Tests for noise memory generation."""

    def test_correct_file_count(self, dataset_dir):
        """100 noise files should be generated."""
        noise_dir = dataset_dir / "noise"
        files = list(noise_dir.glob("*.md"))
        assert len(files) == 100

    def test_noise_frontmatter(self, dataset_dir):
        """Noise files should have YAML frontmatter with access_count."""
        noise_dir = dataset_dir / "noise"
        first_file = next(noise_dir.glob("*.md"))
        content = first_file.read_text(encoding="utf-8")
        parts = content.split("---", 2)
        meta = yaml.safe_load(parts[1])
        assert "access_count" in meta


# ── Flawed procedures ────────────────────────────────────────────


class TestFlawedProcedures:
    """Tests for flawed procedure generation."""

    def test_flawed_procedures_exist(self, dataset_dir):
        """Flawed procedures directory should exist with 3 files."""
        flawed_dir = dataset_dir / "flawed_procedures"
        assert flawed_dir.exists()
        files = list(flawed_dir.glob("*.md"))
        assert len(files) == 3

    def test_flawed_procedures_contain_errors(self, dataset_dir):
        """Flawed procedures should contain intentional error markers."""
        flawed_dir = dataset_dir / "flawed_procedures"
        flaw_markers = {
            "todo", "fixme", "placeholder", "未完成", "要修正",
            "wrong_command", "incorrect", "省略",
        }
        for f in flawed_dir.glob("*.md"):
            content = f.read_text(encoding="utf-8").lower()
            has_flaw = any(marker in content for marker in flaw_markers)
            # Also check for HTML comment flaw annotation
            has_annotation = "<!-- flaw:" in content
            assert has_flaw or has_annotation, (
                f"{f.name} doesn't contain any flaw markers"
            )


# ── Queries ──────────────────────────────────────────────────────


class TestQueryGeneration:
    """Tests for query/ground truth generation."""

    def test_queries_json_exists(self, dataset_dir):
        """queries.json should be generated."""
        queries_file = dataset_dir / "queries.json"
        assert queries_file.exists()

    def test_queries_structure(self, dataset_dir):
        """queries.json should contain queries list with expected fields."""
        queries_file = dataset_dir / "queries.json"
        with open(queries_file) as f:
            data = json.load(f)

        assert "queries" in data
        queries = data["queries"]
        assert len(queries) == 20  # 10 factual + 5 episodic + 5 multi-hop

    def test_query_fields(self, dataset_dir):
        """Each query should have id, type, text, and relevant_files."""
        queries_file = dataset_dir / "queries.json"
        with open(queries_file) as f:
            data = json.load(f)

        for q in data["queries"]:
            assert "id" in q, f"Query missing 'id': {q}"
            assert "type" in q, f"Query missing 'type': {q}"
            assert "text" in q, f"Query missing 'text': {q}"
            assert "relevant_files" in q, f"Query missing 'relevant_files': {q}"
            assert isinstance(q["relevant_files"], list)
            assert len(q["relevant_files"]) > 0

    def test_query_types(self, dataset_dir):
        """Queries should cover factual, episodic, and multi-hop types."""
        queries_file = dataset_dir / "queries.json"
        with open(queries_file) as f:
            data = json.load(f)

        types = {q["type"] for q in data["queries"]}
        assert "factual" in types
        assert "episodic" in types
        assert "multi-hop" in types


# ── Determinism ──────────────────────────────────────────────────


class TestDeterminism:
    """Tests for deterministic output with same seed."""

    def test_same_seed_same_output(self, tmp_path):
        """Two generators with the same seed should produce identical files."""
        dir1 = tmp_path / "run1"
        dir2 = tmp_path / "run2"

        gen1 = AblationDatasetGenerator(output_dir=dir1, seed=42)
        gen1.generate_all()

        gen2 = AblationDatasetGenerator(output_dir=dir2, seed=42)
        gen2.generate_all()

        # Compare queries.json (most sensitive to randomness)
        q1 = json.loads((dir1 / "queries.json").read_text())
        q2 = json.loads((dir2 / "queries.json").read_text())
        assert q1 == q2

        # Compare knowledge file names
        k1 = sorted(f.name for f in (dir1 / "knowledge").glob("*.md"))
        k2 = sorted(f.name for f in (dir2 / "knowledge").glob("*.md"))
        assert k1 == k2

    def test_different_seed_different_output(self, tmp_path):
        """Two generators with different seeds should produce different results."""
        dir1 = tmp_path / "run1"
        dir2 = tmp_path / "run2"

        gen1 = AblationDatasetGenerator(output_dir=dir1, seed=42)
        gen1.generate_all()

        gen2 = AblationDatasetGenerator(output_dir=dir2, seed=999)
        gen2.generate_all()

        q1 = json.loads((dir1 / "queries.json").read_text())
        q2 = json.loads((dir2 / "queries.json").read_text())
        # Episodic queries use random dates, so they should differ
        assert q1 != q2
