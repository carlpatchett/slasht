"""Shared paths for the eval package."""

from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
FIXTURE = EVALS_DIR / "messy_codebase"
GROUND_TRUTH_PATH = EVALS_DIR / "ground_truth.json"
