"""Schema validation, allow-lists, and guard for model output."""

from __future__ import annotations

import json
import re
from typing import Any
from pydantic import BaseModel, Field

from pipewitness.contracts import Contract, ContractSuite, SinkDef


class UnresolvedItem(BaseModel, extra="forbid"):
    quote: str
    reason: str


class RawModelOutput(BaseModel, extra="forbid"):
    contracts: list[Contract] = Field(default_factory=list)
    unresolved: list[UnresolvedItem] = Field(default_factory=list)


def strip_code_fences(text: str) -> str:
    """Strip markdown json code fences if present."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text


def validate_response(raw_text: str, inventory: Any) -> RawModelOutput:
    """Validate raw model response string against schema and inventory, raising ValueError on error."""
    clean_text = strip_code_fences(raw_text)
    try:
        data = json.loads(clean_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON syntax error: {str(e)}") from e

    if not isinstance(data, dict):
        raise ValueError("Root of model output must be a JSON object")

    try:
        model_out = RawModelOutput.model_validate(data)
    except Exception as e:
        raise ValueError(f"Schema validation error: {str(e)}") from e

    # Number of contracts
    if len(model_out.contracts) > 12:
        raise ValueError(f"Too many contracts proposed: {len(model_out.contracts)} > 12")

    # Duplicate IDs
    seen_ids = set()
    for c in model_out.contracts:
        if c.id in seen_ids:
            raise ValueError(f"Duplicate contract ID '{c.id}'")
        seen_ids.add(c.id)

    # Allowed inventories
    # Sinks in inventory can be either exporter names or logical sinks e.g. ["siem", "analytics", "file/siem", "file/analytics"]
    inv_sinks = set()
    if hasattr(inventory, "sinks"):
        for s in inventory.sinks:
            inv_sinks.add(s)
            inv_sinks.add(s.replace("file/", ""))
    else:
        inv_sinks = {"siem", "analytics"}

    # Canaries
    inv_canaries = set(getattr(inventory, "canary_names", []))

    # Keys by scope
    inv_keys_by_scope = getattr(inventory, "fixture_keys_by_scope", {})
    all_known_keys = set()
    for scope_keys in inv_keys_by_scope.values():
        all_known_keys.update(scope_keys)

    for c in model_out.contracts:
        if c.source is None:
            raise ValueError(f"Contract {c.id}: missing source citation")

        # Check sinks
        target_sinks = c.get_target_sinks()
        if not target_sinks:
            raise ValueError(f"Contract {c.id}: no valid sinks specified")
        for s in target_sinks:
            if s not in inv_sinks:
                raise ValueError(f"Contract {c.id}: unknown sink '{s}'")

        # Check canaries
        if c.type == "forbidden_value":
            if not c.canaries:
                raise ValueError(f"Contract {c.id}: forbidden_value requires at least one canary")
            for can in c.canaries:
                if can not in inv_canaries:
                    raise ValueError(f"Contract {c.id}: unknown canary '{can}'")

        # Check field
        if c.type == "preserve_field":
            if not c.field:
                raise ValueError(f"Contract {c.id}: preserve_field requires field specification")
            if c.field.scope not in ("log", "resource", "record"):
                raise ValueError(f"Contract {c.id}: invalid field scope '{c.field.scope}'")
            scope_keys = inv_keys_by_scope.get(c.field.scope, [])
            if c.field.key not in scope_keys:
                raise ValueError(f"Contract {c.id}: unknown key '{c.field.key}' in scope '{c.field.scope}'")

        # Check when.has_attribute
        if c.when and c.when.has_attribute:
            w_scope = c.when.has_attribute.get("scope")
            w_key = c.when.has_attribute.get("key")
            if w_scope not in ("log", "resource", "record"):
                raise ValueError(f"Contract {c.id}: invalid selector scope '{w_scope}'")
            scope_keys = inv_keys_by_scope.get(w_scope, [])
            if w_key not in scope_keys:
                raise ValueError(f"Contract {c.id}: unknown selector key '{w_key}' in scope '{w_scope}'")

    return model_out


def guard_compiler_output(
    raw_text: str,
    allowed_sinks: list[str],
    allowed_canaries: list[str],
    allowed_keys: dict[str, list[str]],
) -> tuple[bool, ContractSuite | None, list[str], dict[str, Any]]:
    """Validate model output against schema and allow-lists."""
    clean_text = strip_code_fences(raw_text)
    try:
        data = json.loads(clean_text)
    except json.JSONDecodeError as e:
        return False, None, [f"JSON syntax error: {str(e)}"], {}

    from pipewitness.inventory import ConfigInventory
    inv = ConfigInventory(
        sinks=allowed_sinks,
        canary_names=allowed_canaries,
        fixture_keys_by_scope=allowed_keys,
    )
    try:
        model_out = validate_response(raw_text, inv)
        sink_defs = {s: SinkDef(exporter=f"file/{s}", external=True) for s in allowed_sinks}
        suite = ContractSuite(sinks=sink_defs, contracts=model_out.contracts)
        return True, suite, [], data
    except ValueError as e:
        return False, None, [str(e)], data
