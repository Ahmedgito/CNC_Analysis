"""The structured answer contract every LLM provider must return.

All fields are required (optional ones are nullable), and no extra keys are allowed, so the same
schema works for Anthropic structured outputs and Groq strict ``json_schema`` mode.
"""

from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DraftStatus = Literal[
    "answered", "not_in_record", "needs_computation", "clarify", "refused_injection"
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceItem(_Strict):
    cell_id: str = Field(description="Exact cell id from the record, e.g. mfg_record_A!Parts!C2")
    quoted_value: str = Field(description="The cell's value copied exactly as shown in the record")


class ComputationInput(_Strict):
    name: str = Field(description="Variable name used in the expression: c1, c2, ...")
    cell_id: str
    number_index: int = Field(
        description="Which number inside the cell value to use, 0-based (Ø125 x 25 -> 0 is 125)"
    )


class Computation(_Strict):
    expression: str = Field(
        description="Arithmetic over the input names only, e.g. 'c1 + c2 + c3' or 'c1 + c2 * c3'"
    )
    inputs: list[ComputationInput]
    unit_in: str | None = Field(description="Unit of the inputs (mm, in, min, h, µm, µin) or null")
    unit_out: str | None = Field(description="Unit to convert the result to, or null")
    label: str = Field(description="Short name of the quantity, e.g. 'total setup time'")


class AnswerDraft(_Strict):
    status: DraftStatus
    answer: str = Field(
        description=(
            "Plain-language answer in markdown. For needs_computation write {result} where the "
            "computed value goes. For not_in_record say what is missing."
        )
    )
    evidence: list[EvidenceItem]
    computation: Computation | None
    general_knowledge: list[str] = Field(
        description="Background explanations NOT taken from the files (kept visibly separate)"
    )
    missing_information: list[str] = Field(
        description="What the user asked for that the record does not contain"
    )
    confidence: Literal["high", "medium", "low"]
    reason: str = Field(description="One sentence on why this status was chosen")


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON schema for providers with strict structured outputs (Groq).

    Every object lists all properties as required and forbids extra keys; ``default`` and
    ``title`` keys are dropped because some strict validators reject them.
    """
    schema = copy.deepcopy(model.model_json_schema())

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("default", None)
            node.pop("title", None)
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(schema)
    return schema
