# Comparison with Existing Tools

| Tool | Focus | Real Collector Execution? | Mutation Testing? | AI Role |
|---|---|---|---|---|
| **OTelBin** | YAML syntax validation & visualization | No (WebAssembly simulator / syntax check) | No | None |
| **OddDotNet** | Pipeline configuration assistant | No | No | Chat assistant |
| **Tracetest** | Trace-based integration testing | Yes (agent instrumented against real service) | No | None |
| **otel-policy-lab** | Policy checks against collector config AST | No (Static AST analysis) | No | None |
| **Collector Testbed** | Go integration testbed for Collector components | Yes (Go unit/integration harness) | No | None |
| **PIPEWITNESS** | Pre-deployment contract verification & test adequacy | **Yes (Docker otelcol-contrib)** | **Yes (Round-trip structure-aware mutations)** | **Gemma 4 proposes contracts & patches (Never judges verdicts)** |

## Why PIPEWITNESS is Unique
1. **Never Simulates in the Verdict Path:** Many tools evaluate OTel Collector logic using regexes or Go re-implementations. PIPEWITNESS runs the actual pinned `otelcol-contrib` container.
2. **Mutation Testing for Telemetry:** Passing tests can give false confidence if the test suite is trivial. PIPEWITNESS breaks collector configs on purpose (dropping processors, perturbing redaction keys, weakening filters) and calculates a test adequacy score.
3. **AI Proposes, Verifier Judges:** Gemma 4 acts as a compiler from requirements/diagrams to contract IR and structured patches. Verdicts (`PASS`, `FAIL`, `INCONCLUSIVE`) are calculated deterministically.
