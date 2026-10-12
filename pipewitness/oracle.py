"""Canary detection oracle for captured telemetry records."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel

from pipewitness.capture import NormalizedRecord


class LeakFinding(BaseModel):
    sink: str
    case_id: str | None
    canary_name: str
    canary_value: str
    scope: str  # log, resource, scope, record
    key: str
    value: str


def _scan_dict_for_canaries(
    d: dict[str, Any],
    canary_map: dict[str, str],
    sink: str,
    case_id: str | None,
    scope: str,
) -> list[LeakFinding]:
    findings = []
    for k, v in d.items():
        v_str = str(v)
        for c_name, c_val in canary_map.items():
            if c_val in v_str:
                findings.append(LeakFinding(
                    sink=sink,
                    case_id=case_id,
                    canary_name=c_name,
                    canary_value=c_val,
                    scope=scope,
                    key=k,
                    value=v_str,
                ))
    return findings


def scan_record_for_canaries(
    record: NormalizedRecord,
    canary_map: dict[str, str],  # canary_name -> canary_value
) -> list[LeakFinding]:
    """Scan all string fields and attribute scopes of a NormalizedRecord for canaries."""
    findings = []

    # 1. log attrs
    findings.extend(_scan_dict_for_canaries(
        record.log_attrs, canary_map, record.sink, record.case_id, "log"
    ))

    # 2. resource attrs
    findings.extend(_scan_dict_for_canaries(
        record.resource_attrs, canary_map, record.sink, record.case_id, "resource"
    ))

    # 3. scope attrs
    findings.extend(_scan_dict_for_canaries(
        record.scope_attrs, canary_map, record.sink, record.case_id, "scope"
    ))

    # 4. record fields (body, trace_id, span_id)
    if record.body:
        for c_name, c_val in canary_map.items():
            if c_val in record.body:
                findings.append(LeakFinding(
                    sink=record.sink,
                    case_id=record.case_id,
                    canary_name=c_name,
                    canary_value=c_val,
                    scope="record",
                    key="body",
                    value=record.body,
                ))

    return findings
