"""Load fixture YAML, expand canary references, build OTLP/HTTP JSON payloads."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from ruamel.yaml import YAML

yaml = YAML()


# --------------- models ---------------

class Canary(BaseModel):
    name: str
    value: str


class Case(BaseModel):
    id: str
    severity: str
    body: str
    trace_id: str | None = None
    span_id: str | None = None
    resource: dict[str, str] = {}
    attributes: dict[str, str] = {}


class FixtureSet(BaseModel):
    canaries: list[Canary]
    cases: list[Case]
    canary_map: dict[str, str] = {}  # name -> value

    @property
    def canary_values(self) -> set[str]:
        return {c.value for c in self.canaries}


# --------------- severity map ---------------

SEVERITY_MAP = {
    "DEBUG": 5, "INFO": 9, "WARN": 13, "ERROR": 17, "FATAL": 21,
}


# --------------- loader ---------------

_CANARY_RE = re.compile(r"\$\{canary\.(\w+)\}")


def _expand_canaries(val: str, canary_map: dict[str, str]) -> str:
    """Replace ${canary.name} references with actual canary values."""
    def _repl(m: re.Match) -> str:
        name = m.group(1)
        if name not in canary_map:
            raise ValueError(f"Unknown canary reference: {name}")
        return canary_map[name]
    return _CANARY_RE.sub(_repl, val)


def _expand_dict(d: dict[str, str], canary_map: dict[str, str]) -> dict[str, str]:
    return {k: _expand_canaries(v, canary_map) if isinstance(v, str) else v for k, v in d.items()}


def load_fixtures(path: Path) -> FixtureSet:
    """Load telemetry.yaml and return expanded fixture set."""
    data = yaml.load(path)
    canary_map = {k: str(v) for k, v in data["canaries"].items()}
    canaries = [Canary(name=k, value=v) for k, v in canary_map.items()]

    cases = []
    for c in data["cases"]:
        cases.append(Case(
            id=c["id"],
            severity=c["severity"],
            body=_expand_canaries(c.get("body", ""), canary_map),
            trace_id=c.get("trace_id"),
            span_id=c.get("span_id"),
            resource=_expand_dict(c.get("resource", {}), canary_map),
            attributes=_expand_dict(c.get("attributes", {}), canary_map),
        ))
    return FixtureSet(canaries=canaries, cases=cases, canary_map=canary_map)


# --------------- OTLP JSON builder ---------------

def _make_kv_list(attrs: dict[str, str]) -> list[dict[str, Any]]:
    """Convert dict to OTLP attribute key-value list."""
    result = []
    for k, v in attrs.items():
        result.append({"key": k, "value": {"stringValue": str(v)}})
    return result


def _severity_number(name: str) -> int:
    return SEVERITY_MAP.get(name.upper(), 9)


def build_otlp_payload(fixtures: FixtureSet) -> dict[str, Any]:
    """Build OTLP/HTTP JSON payload grouping cases by resource."""
    # Group by resource dict (as frozen tuple of items)
    resource_groups: dict[tuple, list[Case]] = {}
    for case in fixtures.cases:
        key = tuple(sorted(case.resource.items()))
        resource_groups.setdefault(key, []).append(case)

    resource_logs = []
    for res_key, cases in resource_groups.items():
        resource_attrs = _make_kv_list(dict(res_key))
        log_records = []
        for case in cases:
            record: dict[str, Any] = {
                "timeUnixNano": str(1_700_000_000_000_000_000),
                "severityNumber": _severity_number(case.severity),
                "severityText": case.severity.upper(),
                "body": {"stringValue": case.body},
                "attributes": _make_kv_list(case.attributes),
            }
            if case.trace_id:
                record["traceId"] = case.trace_id
            if case.span_id:
                record["spanId"] = case.span_id
            log_records.append(record)

        resource_logs.append({
            "resource": {"attributes": resource_attrs},
            "scopeLogs": [{
                "scope": {},
                "logRecords": log_records,
            }],
        })

    return {"resourceLogs": resource_logs}


def payload_json(fixtures: FixtureSet) -> str:
    """Return the OTLP JSON payload as a formatted string."""
    return json.dumps(build_otlp_payload(fixtures), indent=2)
