"""Deterministic arithmetic over cited cells. The LLM proposes, this module computes.

Expressions are parsed with ``ast`` and only a whitelist of nodes is evaluated (numbers, the
declared input names, + - * /, unary minus, and sum/min/max/abs/round). No ``eval``. Unit
conversion uses pint. The result comes with a human-readable working line.
"""

from __future__ import annotations

import ast
import math
import operator
import re
from dataclasses import dataclass, field
from functools import lru_cache

from app.domain.evidence import Fact
from app.llm.schemas import Computation

MAX_EXPRESSION_CHARS = 300
# A number not glued to a letter or digit on its left:
# "Ø125" -> 125, "SS304" -> none, "M10" -> none. Inch drawings write ".010" for 0.010.
_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9.])[-+]?(?:\d+(?:\.\d+)?|\.\d+)")
_UNIT_NAMES = {
    "mm": "millimeter",
    "cm": "centimeter",
    "m": "meter",
    "in": "inch",
    "inch": "inch",
    "inches": "inch",
    "µm": "micrometer",
    "um": "micrometer",
    "μm": "micrometer",
    "µin": "microinch",
    "uin": "microinch",
    "min": "minute",
    "h": "hour",
    "hr": "hour",
    "s": "second",
    "kg": "kilogram",
    "g": "gram",
    "lb": "pound",
}
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_FUNCS = {
    "sum": lambda *a: math.fsum(a),
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
}


class ComputeError(ValueError):
    """The computation cannot be performed safely from the cited cells."""


@dataclass(slots=True)
class ComputedInput:
    name: str
    fact_id: str
    value: str
    number: float


@dataclass(slots=True)
class ComputeResult:
    value: float
    display: str
    unit: str | None
    working: str
    inputs: list[ComputedInput]
    constants: list[float] = field(default_factory=list)


def extract_numbers(text: str) -> list[float]:
    return [float(m.group(0)) for m in _NUMBER_RE.finditer(text)]


def format_number(value: float) -> str:
    if math.isclose(value, round(value), abs_tol=1e-9):
        return str(round(value))
    return f"{value:.4f}".rstrip("0").rstrip(".")


@lru_cache(maxsize=1)
def _ureg():
    import pint

    return pint.UnitRegistry()


def convert(value: float, unit_in: str, unit_out: str) -> float:
    src, dst = _UNIT_NAMES.get(unit_in.strip()), _UNIT_NAMES.get(unit_out.strip())
    if not src or not dst:
        raise ComputeError(f"unsupported unit conversion {unit_in} -> {unit_out}")
    ureg = _ureg()
    try:
        return float(ureg.Quantity(value, src).to(dst).magnitude)
    except Exception as exc:  # pint.DimensionalityError and friends
        raise ComputeError(f"cannot convert {unit_in} to {unit_out}: {exc}") from exc


def _eval(node: ast.AST, names: dict[str, float], constants: list[float]) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body, names, constants)
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int | float)
        and not isinstance(node.value, bool)
    ):
        constants.append(float(node.value))
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id not in names:
            raise ComputeError(f"unknown name '{node.id}' in expression")
        return names[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left = _eval(node.left, names, constants)
        right = _eval(node.right, names, constants)
        if isinstance(node.op, ast.Div) and right == 0:
            raise ComputeError("division by zero")
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
        val = _eval(node.operand, names, constants)
        return -val if isinstance(node.op, ast.USub) else val
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _FUNCS
        and not node.keywords
        and node.args
    ):
        args = [_eval(a, names, constants) for a in node.args]
        return float(_FUNCS[node.func.id](*args))
    raise ComputeError(f"disallowed expression element: {type(node).__name__}")


def compute(computation: Computation, facts: dict[str, Fact]) -> ComputeResult:
    expr = computation.expression.strip()
    if not expr or len(expr) > MAX_EXPRESSION_CHARS:
        raise ComputeError("expression is empty or too long")
    if not computation.inputs:
        raise ComputeError("computation has no inputs")

    inputs: list[ComputedInput] = []
    names: dict[str, float] = {}
    for item in computation.inputs:
        if not re.fullmatch(r"[a-z]\w{0,15}", item.name):
            raise ComputeError(f"invalid input name '{item.name}'")
        fact = facts.get(item.fact_id)
        if fact is None:
            raise ComputeError(f"input {item.name} cites unknown fact {item.fact_id}")
        numbers = extract_numbers(fact.value)
        if not 0 <= item.number_index < len(numbers):
            raise ComputeError(
                f"fact {item.fact_id} ('{fact.value}') has no number at index {item.number_index}"
            )
        names[item.name] = numbers[item.number_index]
        inputs.append(
            ComputedInput(item.name, item.fact_id, fact.value, numbers[item.number_index])
        )

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ComputeError(f"expression is not valid arithmetic: {expr}") from exc
    constants: list[float] = []
    value = _eval(tree, names, constants)
    if math.isnan(value) or math.isinf(value):
        raise ComputeError("result is not a finite number")

    substituted = re.sub(
        r"\b[a-z]\w{0,15}\b",
        lambda m: format_number(names[m.group(0)]) if m.group(0) in names else m.group(0),
        expr,
    )
    unit = computation.unit_in
    working = f"{substituted} = {format_number(value)}" + (f" {unit}" if unit else "")
    if computation.unit_out and computation.unit_in and computation.unit_out != computation.unit_in:
        factor = convert(1.0, computation.unit_in, computation.unit_out)
        for c in constants:
            if c and any(math.isclose(c, f, rel_tol=2e-3) for f in (factor, 1 / factor)):
                raise ComputeError(
                    f"the expression already applies the {computation.unit_in}->"
                    f"{computation.unit_out} factor ({c:g}) and unit_out converts again; remove "
                    "the factor from the expression"
                )
        converted = convert(value, computation.unit_in, computation.unit_out)
        working += f" = {format_number(converted)} {computation.unit_out}"
        value, unit = converted, computation.unit_out
    elif computation.unit_out and not computation.unit_in:
        raise ComputeError("cannot convert: the input unit is not stated in the record")

    display = format_number(value) + (f" {unit}" if unit else "")
    return ComputeResult(value, display, unit, working, inputs, constants)
