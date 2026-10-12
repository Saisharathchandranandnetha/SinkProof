"""Versioned prompt templates for Gemma 4 contract compiler."""

from __future__ import annotations

import json
from typing import Any

PROMPT_VERSION = "2026-10-12.v1"

COMPILER_SYSTEM_INSTRUCTION = """You are a telemetry contract compiler for OpenTelemetry observability pipelines.
You analyze an architecture diagram image and plain-English requirements text to propose structured Telemetry Contracts (IR).

CRITICAL CONSTRAINTS:
1. ONLY propose contracts using the provided inventory (sinks, canaries, keys, types).
2. NEVER guess or invent sink IDs, canary names, or field scopes not in the inventory.
3. Every contract MUST include a 'source' object specifying whether it came from 'text' or 'diagram' and the exact quote.
4. Output STRICT JSON only conforming to the schema below.
"""

def build_compiler_prompt(
    requirements_text: str,
    inventory: dict[str, Any],
) -> str:
    inventory_json = json.dumps(inventory, indent=2)
    return f"""Analyze the provided architecture diagram image and the following plain-English requirements.

Plain-English Requirements:
\"\"\"
{requirements_text}
\"\"\"

Allowed Inventory:
{inventory_json}

Your goal:
Generate machine-checkable Telemetry Contracts for this pipeline.
Allowed Contract Types:
- forbidden_value: forbids canary values from appearing in listed sinks (e.g. passwords, tokens, emails).
- must_reach: ensures selected records reach a sink (e.g. ERROR logs reach SIEM, all reach analytics).
- must_not_reach: ensures selected records do NOT reach a sink (e.g. debug noise not in SIEM).
- preserve_field: ensures critical attributes survive transformation (e.g. request.id, trace_id).

JSON Output Schema:
{{
  "contracts": [
    {{
      "id": "kebab-case-unique-id",
      "type": "forbidden_value" | "must_reach" | "must_not_reach" | "preserve_field",
      "severity": "critical" | "high" | "medium" | "low",
      "sinks": ["sink_id", ...],
      "sink": "sink_id" (if single sink),
      "canaries": ["canary_name", ...],
      "field": {{"scope": "log" | "resource" | "record", "key": "key_name"}},
      "when": {{
        "all": true | false,
        "severity_at_least": "ERROR" | "WARN" | "INFO",
        "severity_below": "WARN" | "INFO"
      }},
      "source": {{
        "kind": "text" | "diagram",
        "quote": "verbatim text or label from input"
      }},
      "status": "ready"
    }}
  ],
  "unresolved": [
    {{
      "quote": "phrase that cannot be modeled",
      "reason": "why it cannot be modeled with available inventory"
    }}
  ]
}}

Respond with valid JSON only. Do not wrap in markdown or commentary.
"""

def build_repair_prompt(
    raw_response: str,
    validation_errors: list[str],
) -> str:
    errs = "\n".join(f"- {e}" for e in validation_errors)
    return f"""Your previous JSON output failed validation with the following errors:
{errs}

Previous output:
\"\"\"
{raw_response}
\"\"\"

Please fix the validation errors and output the corrected JSON adhering strictly to the schema and allowed inventory. Respond with valid JSON only.
"""
