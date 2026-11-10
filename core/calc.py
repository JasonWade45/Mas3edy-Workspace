"""Safe arithmetic calculator used as a verifiable tool for the assistant.

Uses AST whitelisting instead of ``eval`` so model output can never execute
arbitrary code. Supports + - * / // % ** parentheses, unary minus and common
math functions on a strict allow-list.
"""

from __future__ import annotations

import ast
import math
import operator

MAX_EXPRESSION_CHARS = 200
MAX_ABS_VALUE = 1e15
_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_ALLOWED_FUNCS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
    "floor": math.floor,
    "ceil": math.ceil,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
}
_ALLOWED_CONSTS = {"pi": math.pi, "e": math.e}


def _check(value: float) -> float:
    if isinstance(value, complex) or not math.isfinite(value):
        raise ValueError("النتيجة خارج النطاق المسموح.")
    if abs(value) > MAX_ABS_VALUE:
        raise ValueError("النتيجة أكبر من الحد المسموح.")
    return value


def evaluate(expression: str) -> float:
    if not isinstance(expression, str):
        raise TypeError("التعبير لازم يكون نصًا.")
    expression = expression.strip()
    if not expression or len(expression) > MAX_EXPRESSION_CHARS:
        raise ValueError("التعبير فارغ أو أطول من الحد المسموح (200 حرف).")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"تعذر فهم التعبير: {exc.msg}") from exc

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise ValueError("أرقام فقط مسموح بها.")
            return float(node.value)
        if isinstance(node, ast.BinOp):
            op = _ALLOWED_BINOPS.get(type(node.op))
            if op is None:
                raise ValueError("العملية غير مدعومة.")
            left = _eval(node.left)
            right = _eval(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 64:
                raise ValueError("الأس أكبر من الحد المسموح.")
            return _check(op(left, right))
        if isinstance(node, ast.UnaryOp):
            op = _ALLOWED_UNARY.get(type(node.op))
            if op is None:
                raise ValueError("الإشارة غير مدعومة.")
            return _check(op(_eval(node.operand)))
        if isinstance(node, ast.Name):
            if node.id in _ALLOWED_CONSTS:
                return _ALLOWED_CONSTS[node.id]
            raise ValueError(f"الرمز غير معروف: {node.id}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
                raise ValueError("الدالة غير مدعومة.")
            if node.keywords:
                raise ValueError("وسائط مسماة غير مدعومة.")
            args = [_eval(arg) for arg in node.args]
            return _check(float(_ALLOWED_FUNCS[node.func.id](*args)))
        raise ValueError("صيغة غير مدعومة في التعبير.")

    try:
        return _eval(tree)
    except ZeroDivisionError as exc:
        raise ValueError("القسمة على صفر غير مسموحة.") from exc


def format_result(value: float) -> str:
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return f"{value:.10g}"
