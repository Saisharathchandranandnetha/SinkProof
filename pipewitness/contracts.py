"""Telemetry Contract IR (Pydantic v2) + YAML load/dump."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
from pydantic import BaseModel, Field
from ruamel.yaml import YAML

yaml = YAML()
yaml.preserve_quotes = True


class SinkDef(BaseModel):
    exporter: str
    external: bool = True


class WhenCondition(BaseModel):
    all: bool = False
    cases: list[str] | None = None
    severity_at_least: str | None = None
    severity_below: str | None = None
    has_attribute: dict[str, str] | None = None  # {scope, key}


class FieldSpec(BaseModel):
    scope: Literal["log", "resource", "record"]
    key: str


class SourceCitation(BaseModel, extra="forbid"):
    kind: Literal["text", "diagram"]
    quote: str


class Contract(BaseModel, extra="forbid"):
    id: str
    type: Literal["forbidden_value", "must_reach", "must_not_reach", "preserve_field"]
    severity: Literal["critical", "high", "medium", "low"] = "high"
    sinks: list[str] = Field(default_factory=list)
    sink: str | None = None
    canaries: list[str] = Field(default_factory=list)
    field: FieldSpec | None = None
    when: WhenCondition | None = None
    source: SourceCitation | None = None
    status: Literal["ready", "review_required"] = "ready"

    def get_target_sinks(self) -> list[str]:
        if self.sinks:
            return self.sinks
        if self.sink:
            return [self.sink]
        return []


class ContractSuite(BaseModel):
    version: str = "pipewitness/v0"
    sinks: dict[str, SinkDef]
    contracts: list[Contract]


def load_contracts(path: Path) -> ContractSuite:
    """Load contracts from YAML file."""
    data = yaml.load(path)
    return ContractSuite.model_validate(data)


def dump_contracts(suite: ContractSuite, path: Path) -> None:
    """Dump contracts to YAML file."""
    raw = suite.model_dump(exclude_none=True)
    yaml.dump(raw, path)
