"""MinHash signatures and the LSH clone index."""

import pytest

from clone_catcher.config import Settings
from clone_catcher.signature import CloneIndex

from sources import NOISE_CONFIG, NOISE_FIB, PY_A, PY_CLONE


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "orders.py").write_text(PY_A)
    (tmp_path / "fulfilment.py").write_text(PY_CLONE)
    (tmp_path / "numbers.py").write_text(NOISE_FIB)
    (tmp_path / "settings_io.py").write_text(NOISE_CONFIG)
    (tmp_path / "notes.json").write_text('{"ignored": true}')
    (tmp_path / "empty.py").write_text("")
    return tmp_path


@pytest.fixture
def index(workspace):
    return CloneIndex(Settings(root=workspace))


class TestBuild:
    def test_build_indexes_supported_files_only(self, index):
        stats = index.build()
        indexed = set(stats["files"])
        assert indexed == {"orders.py", "fulfilment.py", "numbers.py", "settings_io.py"}
        assert stats["skipped"] == ["empty.py"]

    def test_build_is_idempotent(self, index):
        first = index.build()
        second = index.build()
        assert first["files"] == second["files"]


class TestSimilarity:
    def test_exact_clone_similarity_is_high(self, index):
        index.build()
        similarity = index.similarity("orders.py", "fulfilment.py")
        assert similarity >= 0.9

    def test_unrelated_similarity_is_low(self, index):
        index.build()
        for noise in ("numbers.py", "settings_io.py"):
            assert index.similarity("orders.py", noise) < 0.5


class TestFindClones:
    def test_returns_only_the_structural_twin(self, index):
        index.build()
        matches = index.find_clones("orders.py", threshold=0.9)
        assert [m["path"] for m in matches] == ["fulfilment.py"]
        assert matches[0]["similarity"] >= 0.9

    def test_results_respect_threshold_and_ordering(self, index):
        index.build()
        matches = index.find_clones("orders.py", threshold=0.4)
        assert len(matches) >= 1
        similarities = [m["similarity"] for m in matches]
        assert similarities == sorted(similarities, reverse=True)
        assert all(s >= 0.4 for s in similarities)

    def test_query_unindexed_file_computes_signature_on_the_fly(self, index, workspace):
        index.build()
        (workspace / "late_twin.py").write_text(PY_CLONE.replace("fulfil_request", "dispatch"))
        matches = index.find_clones("late_twin.py", threshold=0.9)
        assert "orders.py" in [m["path"] for m in matches]

    def test_empty_file_reports_no_clones(self, index):
        index.build()
        assert index.find_clones("empty.py", threshold=0.9) == []


class TestDeterminism:
    def test_repeated_builds_produce_identical_results(self, workspace):
        first = CloneIndex(Settings(root=workspace))
        second = CloneIndex(Settings(root=workspace))
        assert first.build()["files"] == second.build()["files"]
        assert (
            first.find_clones("orders.py", threshold=0.9)
            == second.find_clones("orders.py", threshold=0.9)
        )
