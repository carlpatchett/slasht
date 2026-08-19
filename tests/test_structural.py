"""Structural tokenization invariants: the skeleton extractor.

The core promise: renaming identifiers and changing literals, comments, and
whitespace leaves the token stream unchanged; changing structure or operators
does not.
"""

from sources import (
    CS_A,
    CS_CLONE,
    GO_A,
    GO_CLONE,
    PY_A,
    PY_ADDED_BRANCH,
    PY_CLONE,
    PY_LITERALS_ONLY,
)

from clone_catcher.parsing import detect_language, parse_source
from clone_catcher.structural import structural_tokens, token_types


def stream(source: str, language: str = "python") -> list[str]:
    tree = parse_source(language, source.encode("utf-8"))
    return token_types(structural_tokens(tree.root_node))


class TestLanguageDetection:
    def test_supported_extensions(self):
        assert detect_language("pkg/mod.py") == "python"
        assert detect_language("cmd/tool.go") == "go"
        assert detect_language("src/Mailer.cs") == "csharp"

    def test_unsupported_extension_returns_none(self):
        assert detect_language("notes.json") is None
        assert detect_language("README.md") is None


class TestRenameAndLiteralInvariance:
    def test_renamed_clone_has_identical_stream(self):
        assert stream(PY_A) == stream(PY_CLONE)

    def test_literal_changes_preserve_stream(self):
        assert stream(PY_A) == stream(PY_LITERALS_ONLY)

    def test_go_renamed_clone_has_identical_stream(self):
        assert stream(GO_A, "go") == stream(GO_CLONE, "go")

    def test_csharp_renamed_clone_has_identical_stream(self):
        assert stream(CS_A, "csharp") == stream(CS_CLONE, "csharp")


class TestStructuralSensitivity:
    def test_added_branch_alters_stream(self):
        assert stream(PY_A) != stream(PY_ADDED_BRANCH)

    def test_operator_semantics_are_captured(self):
        plus = stream("def f(a, b):\n    return a + b\n")
        minus = stream("def f(a, b):\n    return a - b\n")
        assert plus != minus

    def test_different_languages_produce_different_streams(self):
        py = stream("def f(x):\n    return x + 1\n")
        go = stream("package p\n\nfunc f(x int) int {\n\treturn x + 1\n}\n", "go")
        assert py != go


class TestRobustness:
    def test_parse_error_yields_tokens_without_raising(self):
        tokens = stream("def broken(:\n  return ???\n")
        assert isinstance(tokens, list)

    def test_empty_source_yields_empty_stream(self):
        assert stream("") == []
        assert stream("# just a comment\n") == []

    def test_tokens_carry_source_line_spans(self):
        tree = parse_source("python", PY_A.encode("utf-8"))
        tokens = structural_tokens(tree.root_node)
        assert tokens, "expected non-trivial source to yield tokens"
        for token in tokens:
            assert 1 <= token.start_line <= token.end_line


class TestSkeletonContent:
    def test_stream_contains_structural_node_types(self):
        tokens = stream(PY_A)
        assert "if_statement" in tokens
        assert "return_statement" in tokens
        assert "call" in tokens

    def test_stream_excludes_identifier_text(self):
        tokens = stream(PY_A)
        assert "identifier" not in tokens
        assert "process_order" not in tokens

    def test_stream_excludes_literals(self):
        tokens = stream(PY_A)
        assert "string" not in tokens
        assert "missing" not in tokens
