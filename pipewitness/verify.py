"""Deterministic contract verifier with non-vacuity enforcement."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pipewitness.capture import NormalizedRecord
from pipewitness.contracts import Contract, ContractSuite, WhenCondition
from pipewitness.evidence import EvidenceRecord, FieldFinding, VerificationSummary
from pipewitness.fixtures import Case, FixtureSet, SEVERITY_MAP
from pipewitness.localize import localize_fault
from pipewitness.oracle import scan_record_for_canaries


def _case_matches_when(case: Case, when: WhenCondition | None) -> bool:
    if not when:
        return True
    if when.all:
        return True
    if when.cases is not None:
        return case.id in when.cases

    case_sev_num = SEVERITY_MAP.get(case.severity.upper(), 9)

    if when.severity_at_least:
        target_sev = SEVERITY_MAP.get(when.severity_at_least.upper(), 0)
        if case_sev_num < target_sev:
            return False

    if when.severity_below:
        target_sev = SEVERITY_MAP.get(when.severity_below.upper(), 99)
        if case_sev_num >= target_sev:
            return False

    if when.has_attribute:
        scope = when.has_attribute.get("scope", "log")
        key = when.has_attribute.get("key", "")
        if scope == "log" and key not in case.attributes:
            return False
        if scope == "resource" and key not in case.resource:
            return False

    return True


def _get_field_from_case(case: Case, scope: str, key: str) -> Any:
    if scope == "log":
        return case.attributes.get(key)
    if scope == "resource":
        return case.resource.get(key)
    if scope == "record":
        if key == "trace_id":
            return case.trace_id
        if key == "span_id":
            return case.span_id
        if key == "body":
            return case.body
        if key == "severity_number":
            return SEVERITY_MAP.get(case.severity.upper(), 9)
    return None


def _get_field_from_record(record: NormalizedRecord, scope: str, key: str) -> Any:
    if scope == "log":
        return record.log_attrs.get(key)
    if scope == "resource":
        return record.resource_attrs.get(key)
    if scope == "record":
        if key == "trace_id":
            return record.trace_id
        if key == "span_id":
            return record.span_id
        if key == "body":
            return record.body
        if key == "severity_number":
            return record.severity_number
    return None


def _case_carries_canary(case: Case, canary_value: str) -> tuple[str, str, str] | None:
    """Return (scope, key, value) if case carries canary."""
    for k, v in case.attributes.items():
        if canary_value in str(v):
            return ("log", k, str(v))
    for k, v in case.resource.items():
        if canary_value in str(v):
            return ("resource", k, str(v))
    if canary_value in case.body:
        return ("record", "body", case.body)
    return None


def verify_suite(
    suite: ContractSuite,
    fixtures: FixtureSet,
    captures: list[NormalizedRecord],
    config_path: Path,
    run_meta: dict[str, Any] | None = None,
) -> VerificationSummary:
    """Deterministic evaluation of telemetry contracts against captured records."""
    meta = run_meta or {}
    evidence_records: list[EvidenceRecord] = []
    passed = 0
    failed = 0
    inconclusive = 0

    # Build sink -> exporter map
    sink_to_exporter = {s_id: s_def.exporter for s_id, s_def in suite.sinks.items()}
    # Records grouped by sink
    records_by_sink: dict[str, list[NormalizedRecord]] = {}
    for r in captures:
        records_by_sink.setdefault(r.sink, []).append(r)

    for contract in suite.contracts:
        target_sinks = contract.get_target_sinks()
        contract_verdict: Literal["PASS", "FAIL", "INCONCLUSIVE"] = "PASS"
        contract_evidences: list[EvidenceRecord] = []

        for sink_id in target_sinks:
            exporter = sink_to_exporter.get(sink_id, f"file/{sink_id}")
            sink_records = records_by_sink.get(sink_id, [])
            sink_cases = {r.case_id for r in sink_records if r.case_id}

            # ---------------- 1. forbidden_value ----------------
            if contract.type == "forbidden_value":
                canary_names = contract.canaries
                canary_submap = {c: fixtures.canary_map[c] for c in canary_names if c in fixtures.canary_map}

                # Scan for leaks
                leaks = []
                for rec in sink_records:
                    rec_leaks = scan_record_for_canaries(rec, canary_submap)
                    leaks.extend(rec_leaks)

                if leaks:
                    contract_verdict = "FAIL"
                    for leak in leaks:
                        loc = localize_fault(config_path, exporter, leak.key)
                        contract_evidences.append(EvidenceRecord(
                            contract_id=contract.id,
                            verdict="FAIL",
                            severity=contract.severity,
                            sink=sink_id,
                            exporter=exporter,
                            pipeline=f"logs/{sink_id}",
                            case_id=leak.case_id,
                            canary=leak.canary_name,
                            input=FieldFinding(scope=leak.scope, key=leak.key, value=leak.value),
                            observed=FieldFinding(scope=leak.scope, key=leak.key, value=leak.value),
                            pipeline_path=loc.pipeline_path,
                            localisation=loc,
                            run=meta,
                        ))
                else:
                    # Non-vacuity check: Did >= 1 case that carried ANY of these canaries reach the sink?
                    carrying_case_ids = set()
                    for c in fixtures.cases:
                        for c_val in canary_submap.values():
                            if _case_carries_canary(c, c_val):
                                carrying_case_ids.add(c.id)

                    reached_carrying = carrying_case_ids.intersection(sink_cases)
                    if not reached_carrying:
                        if contract_verdict != "FAIL":
                            contract_verdict = "INCONCLUSIVE"
                        contract_evidences.append(EvidenceRecord(
                            contract_id=contract.id,
                            verdict="INCONCLUSIVE",
                            severity=contract.severity,
                            sink=sink_id,
                            exporter=exporter,
                            pipeline=f"logs/{sink_id}",
                            localisation=localize_fault(config_path, exporter, "canaries"),
                            run=meta,
                        ))

            # ---------------- 2. must_reach ----------------
            elif contract.type == "must_reach":
                selected = [c for c in fixtures.cases if _case_matches_when(c, contract.when)]
                if not selected:
                    contract_verdict = "INCONCLUSIVE"
                    continue

                missing_cases = [c for c in selected if c.id not in sink_cases]
                if missing_cases:
                    contract_verdict = "FAIL"
                    for mc in missing_cases:
                        loc = localize_fault(config_path, exporter, mc.id)
                        contract_evidences.append(EvidenceRecord(
                            contract_id=contract.id,
                            verdict="FAIL",
                            severity=contract.severity,
                            sink=sink_id,
                            exporter=exporter,
                            pipeline=f"logs/{sink_id}",
                            case_id=mc.id,
                            pipeline_path=loc.pipeline_path,
                            localisation=loc,
                            run=meta,
                        ))

            # ---------------- 3. must_not_reach ----------------
            elif contract.type == "must_not_reach":
                selected = [c for c in fixtures.cases if _case_matches_when(c, contract.when)]
                if not selected:
                    contract_verdict = "INCONCLUSIVE"
                    continue

                unwanted_cases = [c for c in selected if c.id in sink_cases]
                if unwanted_cases:
                    contract_verdict = "FAIL"
                    for uc in unwanted_cases:
                        loc = localize_fault(config_path, exporter, uc.id)
                        contract_evidences.append(EvidenceRecord(
                            contract_id=contract.id,
                            verdict="FAIL",
                            severity=contract.severity,
                            sink=sink_id,
                            exporter=exporter,
                            pipeline=f"logs/{sink_id}",
                            case_id=uc.id,
                            pipeline_path=loc.pipeline_path,
                            localisation=loc,
                            run=meta,
                        ))

            # ---------------- 4. preserve_field ----------------
            elif contract.type == "preserve_field":
                if not contract.field:
                    contract_verdict = "INCONCLUSIVE"
                    continue

                scope = contract.field.scope
                key = contract.field.key
                selected = [c for c in fixtures.cases if _case_matches_when(c, contract.when)]
                applicable = [c for c in selected if _get_field_from_case(c, scope, key) is not None]

                # Only cases that reached the sink are evaluated
                reached_applicable = [c for c in applicable if c.id in sink_cases]

                if not reached_applicable:
                    if contract_verdict != "FAIL":
                        contract_verdict = "INCONCLUSIVE"
                    contract_evidences.append(EvidenceRecord(
                        contract_id=contract.id,
                        verdict="INCONCLUSIVE",
                        severity=contract.severity,
                        sink=sink_id,
                        exporter=exporter,
                        pipeline=f"logs/{sink_id}",
                        localisation=localize_fault(config_path, exporter, key),
                        run=meta,
                    ))
                else:
                    for c in reached_applicable:
                        in_val = _get_field_from_case(c, scope, key)
                        matching_records = [r for r in sink_records if r.case_id == c.id]
                        for r in matching_records:
                            out_val = _get_field_from_record(r, scope, key)
                            if out_val is None or str(out_val) != str(in_val):
                                contract_verdict = "FAIL"
                                loc = localize_fault(config_path, exporter, key)
                                contract_evidences.append(EvidenceRecord(
                                    contract_id=contract.id,
                                    verdict="FAIL",
                                    severity=contract.severity,
                                    sink=sink_id,
                                    exporter=exporter,
                                    pipeline=f"logs/{sink_id}",
                                    case_id=c.id,
                                    input=FieldFinding(scope=scope, key=key, value=in_val),
                                    observed=FieldFinding(scope=scope, key=key, value=out_val) if out_val else None,
                                    pipeline_path=loc.pipeline_path,
                                    localisation=loc,
                                    run=meta,
                                ))

        # Aggregate for this contract
        if contract_verdict == "FAIL":
            failed += 1
            evidence_records.extend([e for e in contract_evidences if e.verdict == "FAIL"])
        elif contract_verdict == "INCONCLUSIVE":
            inconclusive += 1
            if contract_evidences:
                evidence_records.extend([e for e in contract_evidences if e.verdict == "INCONCLUSIVE"])
            else:
                evidence_records.append(EvidenceRecord(
                    contract_id=contract.id,
                    verdict="INCONCLUSIVE",
                    severity=contract.severity,
                    sink=target_sinks[0] if target_sinks else "unknown",
                    exporter=sink_to_exporter.get(target_sinks[0], "unknown") if target_sinks else "unknown",
                    pipeline="unknown",
                    run=meta,
                ))
        else:
            passed += 1
            evidence_records.append(EvidenceRecord(
                contract_id=contract.id,
                verdict="PASS",
                severity=contract.severity,
                sink=target_sinks[0] if target_sinks else "unknown",
                exporter=sink_to_exporter.get(target_sinks[0], "unknown") if target_sinks else "unknown",
                pipeline=f"logs/{target_sinks[0]}" if target_sinks else "unknown",
                run=meta,
            ))

    total = len(suite.contracts)
    if failed > 0:
        overall = "FAIL"
    elif inconclusive > 0:
        overall = "INCONCLUSIVE"
    else:
        overall = "PASS"

    return VerificationSummary(
        total_contracts=total,
        passed=passed,
        failed=failed,
        inconclusive=inconclusive,
        overall_verdict=overall,
        evidence_records=evidence_records,
        run_meta=meta,
    )
