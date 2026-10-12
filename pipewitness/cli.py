"""Command-line interface for SINKPROOF."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from pipewitness.capture import parse_captures
from pipewitness.contracts import load_contracts
from pipewitness.fixtures import load_fixtures
from pipewitness.runner import run_collector, validate_config
from pipewitness.verify import verify_suite

app = typer.Typer(help="SINKPROOF: Pre-deployment telemetry contract testing for OpenTelemetry Collector.")
console = Console()


@app.command()
def verify(
    config: Path = typer.Option(..., "--config", "-c", help="Path to Collector config YAML"),
    contracts: Path = typer.Option(..., "--contracts", "-k", help="Path to contracts YAML"),
    telemetry: Path = typer.Option(..., "--telemetry", "-t", help="Path to telemetry fixtures YAML"),
    json_out: Optional[Path] = typer.Option(None, "--json", help="Output verification summary as JSON to file"),
):
    """Run contracts against real Collector execution."""
    console.print(f"[bold blue]PIPEWITNESS[/bold blue] verifying [cyan]{config}[/cyan] with [cyan]{contracts}[/cyan]...")

    # 1. Validate config first
    valid, val_out = validate_config(config)
    if not valid:
        console.print(f"[bold red]INVALID CONFIG:[/bold red] Collector validation failed:\n{val_out}")
        sys.exit(2)

    # 2. Load inputs
    fixture_set = load_fixtures(telemetry)
    suite = load_contracts(contracts)

    # 3. Real collector run
    run_res = run_collector(config, fixture_set)
    if not run_res.success:
        console.print(f"[bold yellow]INCONCLUSIVE:[/bold yellow] Collector run failed: {run_res.error}")
        if run_res.collector_logs:
            console.print(run_res.collector_logs[-500:])
        sys.exit(2)

    # 4. Parse captures
    sink_map = {s_id: s_def.exporter for s_id, s_def in suite.sinks.items()}
    captures = parse_captures(run_res.captures_dir, sink_map)

    # 5. Verify suite
    run_meta = {
        "config_sha256": run_res.config_sha256,
        "fixture_sha256": run_res.fixture_sha256,
        "collector_image": run_res.image_digest or run_res.image,
        "mode": "docker",
    }
    summary = verify_suite(suite, fixture_set, captures, config, run_meta)

    # 6. Render Rich table
    table = Table(title=f"Verification Results ({config.name})")
    table.add_column("Contract ID", style="bold")
    table.add_column("Type")
    table.add_column("Severity")
    table.add_column("Verdict", justify="center")
    table.add_column("Details")

    for c in suite.contracts:
        evs = [e for e in summary.evidence_records if e.contract_id == c.id]
        fails = [e for e in evs if e.verdict == "FAIL"]
        inconcs = [e for e in evs if e.verdict == "INCONCLUSIVE"]

        if fails:
            v_style = "[bold red]FAIL[/bold red]"
            details = []
            for f in fails:
                if f.canary:
                    details.append(f"Leaked '{f.canary}' in {f.case_id} ({f.sink})")
                elif f.input and not f.observed:
                    details.append(f"Missing '{f.input.key}' in {f.case_id} ({f.sink})")
                elif f.case_id:
                    details.append(f"Routing violation case {f.case_id}")
            detail_str = "; ".join(details)
        elif inconcs:
            v_style = "[bold yellow]INCONCLUSIVE[/bold yellow]"
            detail_str = "No applicable case reached sink (vacuous)"
        else:
            v_style = "[bold green]PASS[/bold green]"
            detail_str = "All invariants preserved"

        table.add_row(c.id, c.type, c.severity, v_style, detail_str)

    console.print(table)
    console.print(
        f"Overall: [bold]{summary.overall_verdict}[/bold] "
        f"([green]{summary.passed} PASS[/green], [red]{summary.failed} FAIL[/red], [yellow]{summary.inconclusive} INCONCLUSIVE[/yellow])"
    )

    if json_out:
        json_out.write_text(summary.to_json())
        console.print(f"Summary JSON written to [cyan]{json_out}[/cyan]")

    # Exit code
    if summary.overall_verdict == "FAIL":
        sys.exit(1)
    elif summary.overall_verdict == "INCONCLUSIVE":
        sys.exit(2)
    else:
        sys.exit(0)


@app.command()
def mutate(
    config: Path = typer.Option(..., "--config", "-c", help="Path to Collector config YAML"),
    contracts: Path = typer.Option(..., "--contracts", "-k", help="Path to contracts YAML"),
    telemetry: Path = typer.Option(..., "--telemetry", "-t", help="Path to telemetry fixtures YAML"),
    min_score: float = typer.Option(0.8, "--min-score", help="Minimum required mutation score"),
):
    """Run mutation testing on Collector config and evaluate contract suite strength."""
    from pipewitness.mutate import run_mutations

    console.print(f"[bold magenta]PIPEWITNESS Mutation Engine[/bold magenta] testing [cyan]{config}[/cyan]...")
    result = run_mutations(config, contracts, telemetry)
    result.print_summary(console)

    if result.score < min_score:
        console.print(f"[bold red]FAIL:[/bold red] Mutation score {result.score:.1%} below threshold {min_score:.1%}")
        sys.exit(1)
    else:
        console.print(f"[bold green]PASS:[/bold green] Mutation score {result.score:.1%} meets threshold {min_score:.1%}")
        sys.exit(0)


@app.command()
def compile(
    image: Path = typer.Option(..., "--image", "-i", help="Architecture diagram image"),
    requirements: Path = typer.Option(..., "--requirements", "-r", help="Plain-English requirements text"),
    config: Path = typer.Option(..., "--config", "-c", help="Collector config YAML"),
    telemetry: Path = typer.Option(..., "--telemetry", "-t", help="Telemetry fixtures YAML"),
    output: Path = typer.Option(Path("contracts.yaml"), "-o", "--output", help="Output contracts YAML"),
):
    """Compile telemetry contracts from diagram and requirement using Gemma 4."""
    from pipewitness.ai.gemma import compile_contracts_with_gemma
    from pipewitness.contracts import dump_contracts

    console.print(f"[bold cyan]Compiling contracts with Gemma 4...[/bold cyan]")
    suite, record_mode, diff_str = compile_contracts_with_gemma(
        image_path=image,
        requirements_path=requirements,
        config_path=config,
        telemetry_path=telemetry,
    )
    dump_contracts(suite, output)
    console.print(f"[bold green]Compiled {len(suite.contracts)} contracts ({record_mode}) saved to {output}[/bold green]")
    if diff_str:
        console.print(diff_str)


@app.command()
def fix(
    config: Path = typer.Option(..., "--config", "-c", help="Path to Collector config YAML to fix"),
    contracts: Path = typer.Option(..., "--contracts", "-k", help="Path to contracts YAML"),
    telemetry: Path = typer.Option(..., "--telemetry", "-t", help="Path to telemetry fixtures YAML"),
    output: Path = typer.Option(Path("collector.patched.yaml"), "-o", "--output", help="Output path for patched YAML"),
):
    """Propose structured patch, apply deterministically, and re-verify in sandbox."""
    from pipewitness.ai.remediate import remediate_config

    console.print(f"[bold cyan]Attempting verified remediation for {config}...[/bold cyan]")
    # First verify current
    fixture_set = load_fixtures(telemetry)
    suite = load_contracts(contracts)
    run_res = run_collector(config, fixture_set)
    sink_map = {s_id: s_def.exporter for s_id, s_def in suite.sinks.items()}
    captures = parse_captures(run_res.captures_dir, sink_map)
    summary = verify_suite(suite, fixture_set, captures, config)

    if summary.overall_verdict == "PASS":
        console.print("[green]Config already passes all contracts. No remediation required.[/green]")
        sys.exit(0)

    result = remediate_config(config, contracts, telemetry, summary, output_path=output)
    if result.status == "VERIFIED FIX":
        console.print(f"[bold green]VERIFIED FIX:[/bold green] All contracts pass, mutation score {result.mutation_score:.1%}")
        console.print(f"Patched config saved to: [cyan]{output}[/cyan]")
        sys.exit(0)
    else:
        console.print(f"[bold red]REJECTED PATCH:[/bold red] {result.explanation}")
        sys.exit(1)


@app.command()
def demo():
    """Run full checkout demo end-to-end."""
    console.print("[bold cyan]=== RUNNING PIPEWITNESS DEMO ===[/bold cyan]\n")
    console.print("[yellow]1. Verifying vulnerable config (expect FAIL on leaks & regex):[/yellow]")
    try:
        verify(
            config=Path("examples/checkout/collector.vulnerable.yaml"),
            contracts=Path("examples/checkout/contracts.yaml"),
            telemetry=Path("examples/checkout/telemetry.yaml"),
            json_out=None,
        )
    except SystemExit as e:
        console.print(f"Exit code: {e.code} (as expected for vulnerable config)\n")

    console.print("[green]2. Verifying fixed config (expect all PASS):[/green]")
    try:
        verify(
            config=Path("examples/checkout/collector.fixed.yaml"),
            contracts=Path("examples/checkout/contracts.yaml"),
            telemetry=Path("examples/checkout/telemetry.yaml"),
            json_out=None,
        )
    except SystemExit as e:
        console.print(f"Exit code: {e.code}\n")


if __name__ == "__main__":
    app()
