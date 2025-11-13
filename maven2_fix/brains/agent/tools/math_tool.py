"""
Math Tool
=========

This tool performs basic arithmetic calculations from string expressions
using only the Python standard library.  Only numeric literals and
operators ``+``, ``-``, ``*``, ``/``, ``%``, ``**``, ``(``, ``)`` are
permitted.  The service API supports a single operation ``CALC`` with
an ``expression`` payload and returns the evaluated numeric result.

Example:

>>> service_api({"op": "CALC", "payload": {"expression": "2 * (3 + 4)"}})
{"ok": True, "payload": {"result": 14}}
"""

from __future__ import annotations

import ast
import operator
from typing import Dict, Any


_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _eval_node(node):
    """Recursively evaluate an AST node representing a numeric expression."""
    if isinstance(node, ast.Num):  # type: ignore[attr-defined]
        return node.n
    if isinstance(node, ast.BinOp):  # type: ignore[attr-defined]
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        op_type = type(node.op)
        if op_type not in _BIN_OPS:
            raise ValueError(f"Unsupported operator: {op_type}")
        return _BIN_OPS[op_type](left, right)
    if isinstance(node, ast.UnaryOp):  # type: ignore[attr-defined]
        operand = _eval_node(node.operand)
        op_type = type(node.op)
        if op_type not in _UNARY_OPS:
            raise ValueError(f"Unsupported unary operator: {op_type}")
        return _UNARY_OPS[op_type](operand)
    raise ValueError(f"Unsupported expression component: {node}")


def _safe_calc(expr: str):
    """Parse and safely evaluate a numeric expression."""
    try:
        tree = ast.parse(expr, mode="eval")
    except Exception as e:
        raise ValueError(f"Invalid expression: {e}")
    return _eval_node(tree.body)


def service_api(msg: Dict[str, Any]) -> Dict[str, Any]:
    op = (msg or {}).get("op", "").upper()
    payload = msg.get("payload") or {}
    if op == "CALC":
        expr = payload.get("expression")
        try:
            res = _safe_calc(str(expr))
        except Exception as e:
            return {"ok": False, "error": {"code": "INVALID_EXPRESSION", "message": str(e)}}
        return {"ok": True, "payload": {"result": res}}
    return {"ok": False, "error": {"code": "UNSUPPORTED_OP", "message": op}}