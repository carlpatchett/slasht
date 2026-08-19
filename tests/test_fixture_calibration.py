"""Fixture calibration: the planted clones must actually measure what the
eval claims — planted pairs similar, negatives and cross-group pairs not."""

import itertools
import json
from pathlib import Path

import pytest

from slasht.config import Settings
from slasht.signature import CloneIndex

EVALS = Path(__file__).resolve().parent.parent / "evals"
FIXTURE = EVALS / "messy_codebase"


@pytest.fixture(scope="module")
def ground_truth():
    return json.loads((EVALS / "ground_truth.json").read_text())


@pytest.fixture(scope="module")
def index():
    built = CloneIndex(Settings(root=FIXTURE))
    built.build()
    return built


def test_planted_pairs_meet_minimum_similarity(index, ground_truth):
    for group in ground_truth["groups"]:
        for a, b in itertools.combinations(group["files"], 2):
            similarity = index.similarity(a, b)
            assert similarity >= group["min_similarity"], (
                f"{a} vs {b}: {similarity:.3f} < {group['min_similarity']}"
            )


def test_negative_pairs_stay_well_below_default_threshold(index, ground_truth):
    for a, b in ground_truth["negative_pairs"]:
        similarity = index.similarity(a, b)
        assert similarity < 0.85, (
            f"near-miss pair flagged: {a} vs {b}: {similarity:.3f}"
        )


def test_cross_group_pairs_stay_below_default_threshold(index, ground_truth):
    grouped = [set(g["files"]) for g in ground_truth["groups"]]
    all_files = [f for group in grouped for f in group]
    for a, b in itertools.combinations(sorted(all_files), 2):
        same_group = any(a in group and b in group for group in grouped)
        if same_group:
            continue
        similarity = index.similarity(a, b)
        assert similarity < 0.85, f"cross-group collision: {a} vs {b}: {similarity:.3f}"


def test_find_clones_recovers_every_planted_group(index, ground_truth):
    for group in ground_truth["groups"]:
        probe = group["files"][0]
        found = {
            m["path"]
            for m in index.find_clones(probe, threshold=group["min_similarity"])
        }
        for other in group["files"][1:]:
            assert other in found, f"{other} not recovered from probe {probe}"
