"""Structural tokenization: reduce a syntax tree to its skeleton.

Traversal emits tree-sitter node types (``if_statement``, ``binary_expression``,
``return_statement``, ...) while pruning every node that carries a *value*
rather than *shape*: identifiers, literals, comments. Operator and keyword
tokens are kept because they distinguish skeletons (``+`` vs ``-``, ``and`` vs
``or``); pure grouping punctuation is dropped.

Rename a function, change a string or number, rewrite comments and whitespace:
the skeleton is byte-identical. Add a branch or swap an operator: it changes.
"""

from __future__ import annotations

from dataclasses import dataclass

# Named node types pruned outright (their subtree is value, not structure).
SKIP_EXACT: frozenset[str] = frozenset(
    {
        "identifier",
        "comment",
        "docstring",
        "string",
        "string_content",
        "escape_sequence",
        "interpolation",
        "format_spec",
        "type_conversion",
        "number",
        "integer",
        "float",
        "imaginary",
        "rune",
        "none",
        "true",
        "false",
        "null",
        "nil",
        "boolean",
    }
)

# Suffixes that reliably mark name/literal/comment nodes across grammars
# (type_identifier, field_identifier, int_literal, string_literal, ...).
SKIP_SUFFIXES: tuple[str, ...] = ("_identifier", "_literal", "_comment")

# Unnamed tokens that carry no structural signal (grouping only).
PUNCTUATION: frozenset[str] = frozenset(
    {"(", ")", "[", "]", "{", "}", ",", ":", ";", ".", "...", "@", "\\", "`", "$"}
)


@dataclass(frozen=True)
class StructToken:
    """One skeleton token with its source line span (1-based, inclusive)."""

    type: str
    start_line: int
    end_line: int


def _pruned(node_type: str) -> bool:
    return node_type in SKIP_EXACT or node_type.endswith(SKIP_SUFFIXES)


def structural_tokens(root) -> list[StructToken]:
    """Pre-order DFS over ``root`` collecting skeleton tokens.

    Pruned subtrees are skipped entirely; unnamed children are emitted only
    when they are operators/keywords rather than punctuation.
    """
    tokens: list[StructToken] = []
    # The file wrapper (module / source_file / compilation_unit) is not
    # structure: empty and comment-only files must yield empty skeletons.
    stack = list(reversed(root.children))
    while stack:
        node = stack.pop()
        if not node.is_named:
            if node.type not in PUNCTUATION:
                tokens.append(
                    StructToken(
                        node.type, node.start_point.row + 1, node.end_point.row + 1
                    )
                )
            continue
        if _pruned(node.type):
            continue
        tokens.append(
            StructToken(node.type, node.start_point.row + 1, node.end_point.row + 1)
        )
        stack.extend(reversed(node.children))
    return tokens


def token_types(tokens: list[StructToken]) -> list[str]:
    """The skeleton as a plain token-type sequence."""
    return [token.type for token in tokens]
