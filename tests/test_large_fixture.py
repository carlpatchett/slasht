"""Large-fixture calibration: families must group exactly, noise must not."""

import itertools

import pytest

from slasht.config import Settings
from slasht.signature import CloneIndex
from evals.gen_large_fixture import generate

EXPECTED_FAMILIES = 7


@pytest.fixture(scope="module")
def fixture_dir(tmp_path_factory):
    dest = tmp_path_factory.mktemp("large_fixture") / "meridian"
    ground_truth = generate(dest)
    return dest, ground_truth


@pytest.fixture(scope="module")
def index(fixture_dir):
    dest, _ = fixture_dir
    built = CloneIndex(Settings(root=dest))
    built.build()
    return built


def test_fixture_is_sized_to_punish_reading_everything(fixture_dir):
    _, ground_truth = fixture_dir
    stats = ground_truth["stats"]
    assert stats["indexed_files"] >= 60
    assert stats["approx_lines"] >= 2500
    assert len(ground_truth["groups"]) == EXPECTED_FAMILIES


def test_family_members_share_identical_skeletons(index, fixture_dir):
    _, ground_truth = fixture_dir
    for group in ground_truth["groups"]:
        for a, b in itertools.combinations(group["files"], 2):
            similarity = index.similarity(a, b)
            assert similarity >= 0.99, f"{a} vs {b}: {similarity:.3f}"


def test_cross_family_pairs_stay_below_default_threshold(index, fixture_dir):
    _, ground_truth = fixture_dir
    family_sets = [set(g["files"]) for g in ground_truth["groups"]]
    all_files = sorted(f for group in family_sets for f in group)
    for a, b in itertools.combinations(all_files, 2):
        same = any(a in group and b in group for group in family_sets)
        if same:
            continue
        similarity = index.similarity(a, b)
        assert similarity < 0.85, (
            f"cross-family collision: {a} vs {b}: {similarity:.3f}"
        )


def test_duplicate_groups_recovers_exact_family_partition(index, fixture_dir):
    _, ground_truth = fixture_dir
    result = index.duplicate_groups(threshold=0.9)
    returned = {frozenset(g["files"]) for g in result["groups"]}
    expected = {frozenset(g["files"]) for g in ground_truth["groups"]}
    assert returned == expected
    assert result["truncated"] is False
    sizes = sorted(g["size"] for g in result["groups"])
    assert sizes == sorted(len(g["files"]) for g in ground_truth["groups"])


def test_generator_is_deterministic(tmp_path):
    first = tmp_path / "one"
    second = tmp_path / "two"
    generate(first)
    generate(second)
    left = {
        str(p.relative_to(first)): p.read_bytes()
        for p in first.rglob("*")
        if p.is_file()
    }
    right = {
        str(p.relative_to(second)): p.read_bytes()
        for p in second.rglob("*")
        if p.is_file()
    }
    assert left.keys() == right.keys()
    assert left == right
