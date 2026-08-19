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
    Uses TreeCursor for zero-allocation C-level AST traversal.
    """
    cursor = root.walk()
    tokens: list[StructToken] = []

    if not cursor.goto_first_child():
        return tokens
    while True:
        node_type = str(cursor.node.type)
        is_named = bool(cursor.node.is_named)
        start_row = int(cursor.node.start_point[0] + 1)
        end_row = int(cursor.node.end_point[0] + 1)

        pruned = False
        if not is_named:
            if node_type not in PUNCTUATION:
                tokens.append(StructToken(node_type, start_row, end_row))
        elif _pruned(node_type):
            pruned = True
        else:
            tokens.append(StructToken(node_type, start_row, end_row))

        if not pruned and cursor.goto_first_child():
            continue

        if cursor.goto_next_sibling():
            continue

        backtracked = False
        while cursor.goto_parent():
            if cursor.node == root:
                backtracked = True
                break
            if cursor.goto_next_sibling():
                backtracked = True
                break
        if (backtracked and cursor.node == root) or not backtracked:
            break

    return tokens


def token_types(tokens: list[StructToken]) -> list[str]:
    """The skeleton as a plain token-type sequence."""
    return [token.type for token in tokens]
