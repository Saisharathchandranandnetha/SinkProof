"""Parse file-exporter JSON lines into NormalizedRecords."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class NormalizedRecord(BaseModel):
    """A single normalised log record from a file exporter output."""
    sink: str
    exporter: str
    case_id: str | None = None
    severity_number: int | None = None
    body: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    log_attrs: dict[str, Any] = {}
    resource_attrs: dict[str, Any] = {}
    scope_attrs: dict[str, Any] = {}


_PW_CASE_RE = re.compile(r"\[pw:(\w+)\]")


def _extract_attrs(kv_list: list[dict] | None) -> dict[str, Any]:
    """Convert OTLP key-value list to a flat dict."""
    if not kv_list:
        return {}
    result = {}
    for item in kv_list:
        key = item.get("key", "")
        value_obj = item.get("value", {})
        # Handle different OTLP value types
        if "stringValue" in value_obj:
            result[key] = value_obj["stringValue"]
        elif "intValue" in value_obj:
            result[key] = int(value_obj["intValue"])
        elif "doubleValue" in value_obj:
            result[key] = float(value_obj["doubleValue"])
        elif "boolValue" in value_obj:
            result[key] = bool(value_obj["boolValue"])
        elif "arrayValue" in value_obj:
            result[key] = json.dumps(value_obj["arrayValue"])
        elif "kvlistValue" in value_obj:
            result[key] = json.dumps(value_obj["kvlistValue"])
        else:
            result[key] = str(value_obj)
    return result


def _detect_case_id(record: dict, log_attrs: dict[str, Any]) -> str | None:
    """Detect case identity from pipewitness.case attr or [pw:X] body marker."""
    # Primary: attribute
    if "pipewitness.case" in log_attrs:
        return str(log_attrs["pipewitness.case"])
    # Fallback: body marker
    body_obj = record.get("body", {})
    body_str = body_obj.get("stringValue", "") if isinstance(body_obj, dict) else str(body_obj)
    m = _PW_CASE_RE.search(body_str or "")
    if m:
        return m.group(1)
    return None


def parse_captures(captures_dir: Path, sink_map: dict[str, str]) -> list[NormalizedRecord]:
    """Parse all capture files and return normalized records.
    
    sink_map: exporter_id -> logical sink name (e.g. "file/siem" -> "siem")
    """
    # Invert: we need filename -> sink
    # File exporters write to paths like /captures/siem.jsonl
    # The filename stem should map to the sink
    exporter_to_sink = {v: k for k, v in sink_map.items()}

    records = []
    for jsonl_file in sorted(captures_dir.glob("*.jsonl")):
        # Derive sink from filename: siem.jsonl -> siem
        stem = jsonl_file.stem
        # Find which sink this file belongs to
        sink_name = None
        exporter_name = None
        for s_name, exp_id in sink_map.items():
            # exp_id is like "file/siem" -> file writes to siem.jsonl
            exp_suffix = exp_id.split("/")[-1] if "/" in exp_id else exp_id
            if stem == exp_suffix:
                sink_name = s_name
                exporter_name = exp_id
                break
        if not sink_name:
            # Fallback: use stem as sink name
            sink_name = stem
            exporter_name = f"file/{stem}"

        for line in jsonl_file.read_text().strip().splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            # OTLP export object has resourceLogs
            for rl in obj.get("resourceLogs", []):
                resource_attrs = _extract_attrs(
                    rl.get("resource", {}).get("attributes")
                )
                for sl in rl.get("scopeLogs", []):
                    scope_attrs = _extract_attrs(
                        sl.get("scope", {}).get("attributes")
                    )
                    for lr in sl.get("logRecords", []):
                        log_attrs = _extract_attrs(lr.get("attributes"))
                        body_obj = lr.get("body", {})
                        body = body_obj.get("stringValue", "") if isinstance(body_obj, dict) else str(body_obj)

                        records.append(NormalizedRecord(
                            sink=sink_name,
                            exporter=exporter_name,
                            case_id=_detect_case_id(lr, log_attrs),
                            severity_number=lr.get("severityNumber"),
                            body=body,
                            trace_id=lr.get("traceId"),
                            span_id=lr.get("spanId"),
                            log_attrs=log_attrs,
                            resource_attrs=resource_attrs,
                            scope_attrs=scope_attrs,
                        ))
    return records
