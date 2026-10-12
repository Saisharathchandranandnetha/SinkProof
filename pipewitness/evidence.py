"""Evidence records and rendering for verification verdicts."""

from __future__ import annotations

import json
from typing import Any, Literal
from pydantic import BaseModel

from pipewitness.localize import LocalisationResult


class FieldFinding(BaseModel):
    scope: str
    key: str
    value: Any


class EvidenceRecord(BaseModel):
    contract_id: str
    verdict: Literal["PASS", "FAIL", "INCONCLUSIVE"]
    severity: str
    sink: str
    exporter: str
    pipeline: str
    case_id: str | None = None
    canary: str | None = None
    input: FieldFinding | None = None
    observed: FieldFinding | None = None
    pipeline_path: list[str] = []
    localisation: LocalisationResult | None = None
    run: dict[str, str] = {}


class VerificationSummary(BaseModel):
    total_contracts: int
    passed: int
    failed: int
    inconclusive: int
    overall_verdict: Literal["PASS", "FAIL", "INCONCLUSIVE"]
    evidence_records: list[EvidenceRecord] = []
    run_meta: dict[str, Any] = {}

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    def to_markdown(self) -> str:
        lines = [
            f"# PIPEWITNESS Verification Report",
            f"",
            f"**Overall Verdict:** `{self.overall_verdict}`  ",
            f"**Passed:** {self.passed}/{self.total_contracts} | **Failed:** {self.failed} | **Inconclusive:** {self.inconclusive}",
            f"",
            "## Contract Verdicts",
            "",
            "| Contract ID | Severity | Verdict | Sink | Notes |",
            "|---|---|---|---|---|",
        ]
        seen_contracts = set()
        for ev in self.evidence_records:
            seen_contracts.add(ev.contract_id)
            notes = ""
            if ev.verdict == "FAIL":
                if ev.canary:
                    notes = f"Canary `{ev.canary}` leaked in case `{ev.case_id}`"
                elif ev.input and not ev.observed:
                    notes = f"Field `{ev.input.key}` missing in output"
                elif ev.input and ev.observed:
                    notes = f"Field `{ev.input.key}` value changed"
                else:
                    notes = f"Case `{ev.case_id}` routing violation"
            elif ev.verdict == "INCONCLUSIVE":
                notes = "Vacuous check or execution failure"
            else:
                notes = "Satisfied"
            lines.append(f"| `{ev.contract_id}` | {ev.severity} | **{ev.verdict}** | `{ev.sink}` | {notes} |")

        if self.failed > 0:
            lines.append("")
            lines.append("## Failure Evidence & Fault Localisation")
            for ev in self.evidence_records:
                if ev.verdict == "FAIL":
                    lines.append(f"### Contract: `{ev.contract_id}` ({ev.severity.upper()})")
                    lines.append(f"- **Sink:** `{ev.sink}` ({ev.exporter})")
                    lines.append(f"- **Case:** `{ev.case_id}`")
                    if ev.canary:
                        lines.append(f"- **Canary Leaked:** `{ev.canary}`")
                    if ev.input:
                        lines.append(f"- **Input:** `[{ev.input.scope}] {ev.input.key} = {ev.input.value}`")
                    if ev.observed:
                        lines.append(f"- **Observed:** `[{ev.observed.scope}] {ev.observed.key} = {ev.observed.value}`")
                    if ev.localisation:
                        lines.append(f"- **Pipeline Path:** `{' -> '.join(ev.localisation.pipeline_path)}`")
                        lines.append(f"- **Fault Explanation:** {ev.localisation.explanation}")
                    lines.append("")

        return "\n".join(lines)
