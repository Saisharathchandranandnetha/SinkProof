"""Structure-aware mutation engine for OpenTelemetry Collector YAML."""

from __future__ import annotations

import copy
import difflib
import io
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Literal
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table
from ruamel.yaml import YAML

from pipewitness.capture import parse_captures
from pipewitness.contracts import ContractSuite, load_contracts
from pipewitness.fixtures import FixtureSet, load_fixtures
from pipewitness.runner import run_collector, validate_config
from pipewitness.verify import verify_suite

yaml = YAML()
yaml.preserve_quotes = True


class Mutant(BaseModel):
    id: str
    operator: str  # drop_processor | drop_ottl_statement | perturb_key | weaken_filter
    location: str  # e.g. "service.pipelines.logs/siem.processors[0]"
    diff: str
    mutant_yaml: str
    valid: bool = True
    outcome: Literal["killed", "survived", "invalid", "inconclusive"] = "survived"
    killed_by: list[str] = []


class MutationRunResult(BaseModel):
    config_name: str
    suite_name: str
    total_mutants: int
    valid_mutants: int
    killed: int
    survived: int
    invalid: int
    inconclusive: int
    score: float
    mutants: list[Mutant]

    def print_summary(self, console: Console) -> None:
        table = Table(title=f"Mutation Test Results: {self.config_name} ({self.suite_name})")
        table.add_column("Mutant ID", style="bold")
        table.add_column("Operator")
        table.add_column("Location")
        table.add_column("Outcome", justify="center")
        table.add_column("Killed By / Notes")

        for m in self.mutants:
            if m.outcome == "killed":
                style = "[bold green]KILLED[/bold green]"
                notes = ", ".join(m.killed_by[:2])
                if len(m.killed_by) > 2:
                    notes += f" (+{len(m.killed_by)-2} more)"
            elif m.outcome == "survived":
                style = "[bold red]SURVIVED[/bold red]"
                notes = "Not detected — contract gap or equivalent"
            elif m.outcome == "invalid":
                style = "[yellow]INVALID[/yellow]"
                notes = "Rejected by collector validate"
            else:
                style = "[cyan]INCONCLUSIVE[/cyan]"
                notes = "Collector execution failed"
            table.add_row(m.id, m.operator, m.location, style, notes)

        console.print(table)
        console.print(
            f"Score: [bold]{self.score:.1%}[/bold] "
            f"({self.killed} killed / {self.killed + self.survived} evaluated). "
            f"Invalid: {self.invalid}, Inconclusive: {self.inconclusive}"
        )


def _dump_yaml_str(data: Any) -> str:
    buf = io.StringIO()
    yaml.dump(data, buf)
    return buf.getvalue()


def _compute_diff(original_text: str, mutant_text: str) -> str:
    diff = difflib.unified_diff(
        original_text.splitlines(keepends=True),
        mutant_text.splitlines(keepends=True),
        fromfile="original.yaml",
        tofile="mutant.yaml",
        n=2,
    )
    return "".join(diff)


def generate_mutants(config_path: Path) -> list[Mutant]:
    """Generate mutants using the 4 specified operators."""
    orig_text = config_path.read_text()
    orig_data = yaml.load(orig_text)
    mutants: list[Mutant] = []
    idx = 1

    pipelines = orig_data.get("service", {}).get("pipelines", {})
    processors = orig_data.get("processors", {})

    # 1. Operator: drop_processor
    # Remove processor P from pipeline L (skip batch and memory_limiter)
    for p_id, p_spec in pipelines.items():
        procs = list(p_spec.get("processors", []))
        for p_idx, proc_name in enumerate(procs):
            if any(skip in proc_name for skip in ("batch", "memory_limiter")):
                continue
            mut_data = copy.deepcopy(orig_data)
            del mut_data["service"]["pipelines"][p_id]["processors"][p_idx]
            mut_text = _dump_yaml_str(mut_data)
            diff = _compute_diff(orig_text, mut_text)
            mutants.append(Mutant(
                id=f"MUT-{idx:02d}",
                operator="drop_processor",
                location=f"service.pipelines.{p_id}.processors[{proc_name}]",
                diff=diff,
                mutant_yaml=mut_text,
            ))
            idx += 1

    # 2. Operator: drop_ottl_statement
    # Delete one statement from a transform processor
    for proc_name, proc_def in processors.items():
        if "transform" in proc_name:
            statements_blocks = proc_def.get("log_statements", [])
            for b_idx, block in enumerate(statements_blocks):
                stmts = block.get("statements", [])
                if len(stmts) > 0:
                    for s_idx, stmt in enumerate(stmts):
                        mut_data = copy.deepcopy(orig_data)
                        del mut_data["processors"][proc_name]["log_statements"][b_idx]["statements"][s_idx]
                        mut_text = _dump_yaml_str(mut_data)
                        diff = _compute_diff(orig_text, mut_text)
                        mutants.append(Mutant(
                            id=f"MUT-{idx:02d}",
                            operator="drop_ottl_statement",
                            location=f"processors.{proc_name}.log_statements[{b_idx}].statements[{s_idx}]",
                            diff=diff,
                            mutant_yaml=mut_text,
                        ))
                        idx += 1

    # 3. Operator: perturb_key
    # Change key literal in delete_key(attributes, "...") -> append _x
    for proc_name, proc_def in processors.items():
        if "transform" in proc_name:
            statements_blocks = proc_def.get("log_statements", [])
            for b_idx, block in enumerate(statements_blocks):
                stmts = block.get("statements", [])
                for s_idx, stmt in enumerate(stmts):
                    if 'delete_key(attributes, "' in stmt:
                        mut_data = copy.deepcopy(orig_data)
                        # Replace delete_key(attributes, "foo") with delete_key(attributes, "foo_x")
                        new_stmt = re.sub(
                            r'delete_key\(attributes,\s*"([^"]+)"\)',
                            r'delete_key(attributes, "\1_x")',
                            stmt,
                        )
                        mut_data["processors"][proc_name]["log_statements"][b_idx]["statements"][s_idx] = new_stmt
                        mut_text = _dump_yaml_str(mut_data)
                        diff = _compute_diff(orig_text, mut_text)
                        mutants.append(Mutant(
                            id=f"MUT-{idx:02d}",
                            operator="perturb_key",
                            location=f"processors.{proc_name}.log_statements[{b_idx}].statements[{s_idx}]",
                            diff=diff,
                            mutant_yaml=mut_text,
                        ))
                        idx += 1

    # 4. Operator: weaken_filter
    # Shift SEVERITY_NUMBER_ERROR to SEVERITY_NUMBER_FATAL
    for proc_name, proc_def in processors.items():
        if "filter" in proc_name:
            logs_conf = proc_def.get("logs", {})
            log_records = logs_conf.get("log_record", [])
            for r_idx, cond in enumerate(log_records):
                if "SEVERITY_NUMBER_ERROR" in cond:
                    mut_data = copy.deepcopy(orig_data)
                    new_cond = cond.replace("SEVERITY_NUMBER_ERROR", "SEVERITY_NUMBER_FATAL")
                    mut_data["processors"][proc_name]["logs"]["log_record"][r_idx] = new_cond
                    mut_text = _dump_yaml_str(mut_data)
                    diff = _compute_diff(orig_text, mut_text)
                    mutants.append(Mutant(
                        id=f"MUT-{idx:02d}",
                        operator="weaken_filter",
                        location=f"processors.{proc_name}.logs.log_record[{r_idx}]",
                        diff=diff,
                        mutant_yaml=mut_text,
                    ))
                    idx += 1

    return mutants


def _eval_single_mutant(
    mutant: Mutant,
    contracts: ContractSuite,
    fixtures: FixtureSet,
    scratch_dir: Path,
) -> Mutant:
    """Evaluate one mutant: validate -> run -> verify."""
    mut_file = scratch_dir / f"{mutant.id}.yaml"
    mut_file.write_text(mutant.mutant_yaml)

    # 1. Validate first (invalid != killed!)
    valid, val_out = validate_config(mut_file)
    if not valid:
        mutant.valid = False
        mutant.outcome = "invalid"
        return mutant

    # 2. Run real collector
    run_res = run_collector(mut_file, fixtures)
    if not run_res.success:
        mutant.outcome = "inconclusive"
        return mutant

    # 3. Parse captures and verify
    sink_map = {s_id: s_def.exporter for s_id, s_def in contracts.sinks.items()}
    captures = parse_captures(run_res.captures_dir, sink_map)
    summary = verify_suite(contracts, fixtures, captures, mut_file)

    if summary.failed > 0:
        mutant.outcome = "killed"
        killed_ids = list({e.contract_id for e in summary.evidence_records if e.verdict == "FAIL"})
        mutant.killed_by = killed_ids
    else:
        mutant.outcome = "survived"

    return mutant


def run_mutations(
    config_path: Path,
    contracts_path: Path,
    telemetry_path: Path,
    max_workers: int = 4,
) -> MutationRunResult:
    """Execute mutation testing suite."""
    contracts = load_contracts(contracts_path)
    fixtures = load_fixtures(telemetry_path)
    mutants = generate_mutants(config_path)

    scratch_dir = Path("runs") / "mutation_scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)

    evaluated_mutants: list[Mutant] = []
    # Evaluate mutants
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_eval_single_mutant, m, contracts, fixtures, scratch_dir): m
            for m in mutants
        }
        for fut in as_completed(futures):
            res = fut.result()
            evaluated_mutants.append(res)

    evaluated_mutants.sort(key=lambda x: x.id)

    killed = sum(1 for m in evaluated_mutants if m.outcome == "killed")
    survived = sum(1 for m in evaluated_mutants if m.outcome == "survived")
    invalid = sum(1 for m in evaluated_mutants if m.outcome == "invalid")
    inconclusive = sum(1 for m in evaluated_mutants if m.outcome == "inconclusive")

    denom = killed + survived
    score = (killed / denom) if denom > 0 else 0.0

    return MutationRunResult(
        config_name=config_path.name,
        suite_name=contracts_path.name,
        total_mutants=len(evaluated_mutants),
        valid_mutants=len(evaluated_mutants) - invalid,
        killed=killed,
        survived=survived,
        invalid=invalid,
        inconclusive=inconclusive,
        score=score,
        mutants=evaluated_mutants,
    )
