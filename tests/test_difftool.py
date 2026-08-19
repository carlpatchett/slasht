"""AST-level diff summary between two files."""

from sources import (
    NOISE_FIB,
    PY_A,
    PY_ADDED_BRANCH,
    PY_CLONE,
    PY_LITERALS_ONLY,
)

from clone_catcher.difftool import diff_summary


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    return str(path)


class TestIdenticalStructure:
    def test_renamed_only_clone_is_flagged_identical(self, tmp_path):
        summary = diff_summary(
            write(tmp_path, "a.py", PY_A), write(tmp_path, "b.py", PY_CLONE)
        )
        assert summary["identical_structure"] is True
        assert summary["structural_similarity"] == 1.0
        assert summary["regions"] == []
        assert summary["text_lines_changed"] > 0

    def test_literal_only_change_is_flagged_identical(self, tmp_path):
        summary = diff_summary(
            write(tmp_path, "a.py", PY_A), write(tmp_path, "b.py", PY_LITERALS_ONLY)
        )
        assert summary["identical_structure"] is True


class TestStructuralChanges:
    def test_added_branch_produces_insert_region(self, tmp_path):
        summary = diff_summary(
            write(tmp_path, "a.py", PY_A), write(tmp_path, "b.py", PY_ADDED_BRANCH)
        )
        assert summary["identical_structure"] is False
        assert summary["structural_similarity"] < 1.0
        inserts = [r for r in summary["regions"] if r["kind"] == "insert"]
        assert inserts, "expected at least one insert region"
        region = inserts[0]
        assert region["b_lines"] is not None
        assert any(t.startswith("if_statement") for t in region["node_types"])

    def test_regions_have_valid_line_ranges(self, tmp_path):
        summary = diff_summary(
            write(tmp_path, "a.py", PY_A), write(tmp_path, "b.py", PY_ADDED_BRANCH)
        )
        total_lines_b = len(PY_ADDED_BRANCH.splitlines())
        for region in summary["regions"]:
            for side in ("a_lines", "b_lines"):
                if region[side] is not None:
                    start, end = region[side]
                    assert 1 <= start <= end <= total_lines_b

    def test_similarity_orders_clone_over_unrelated(self, tmp_path):
        clone = diff_summary(
            write(tmp_path, "a.py", PY_A), write(tmp_path, "clone.py", PY_CLONE)
        )
        modified = diff_summary(
            write(tmp_path, "a2.py", PY_A), write(tmp_path, "mod.py", PY_ADDED_BRANCH)
        )
        unrelated = diff_summary(
            write(tmp_path, "a3.py", PY_A), write(tmp_path, "noise.py", NOISE_FIB)
        )
        assert (
            clone["structural_similarity"]
            > modified["structural_similarity"]
            > unrelated["structural_similarity"]
        )


class TestErrors:
    def test_missing_file_raises_value_error(self, tmp_path):
        import pytest

        with pytest.raises(ValueError, match="not found"):
            diff_summary(str(tmp_path / "nope.py"), write(tmp_path, "b.py", PY_A))

    def test_unsupported_file_raises_value_error(self, tmp_path):
        import pytest

        with pytest.raises(ValueError, match="[Uu]nsupported"):
            diff_summary(write(tmp_path, "a.json", "{}"), write(tmp_path, "b.py", PY_A))
