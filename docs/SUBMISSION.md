# SinkProof — Hacktoberfest Hack Day 2026 Submission

> **Prove your telemetry pipeline before production.**

SinkProof is an open-source pre-deployment verification harness for OpenTelemetry Collector pipelines. It turns human security and data-integrity intent into executable telemetry contracts, executes those contracts against a real Collector, and mutation-tests the pipeline to measure whether the test suite can actually catch regressions.

---

## Team / attendee

- **Team name:** SinkProof
- **Member:** Saisharathchandranandnetha — @Saisharathchandranandnetha
- **Profile:** https://github.com/Saisharathchandranandnetha
- **Format:** Solo build
- **Event:** Hacktoberfest Hack Day 2026 — NIAT-KKH × MLH

---

## Challenge

- [x] Best Open-Source AI Project
- [x] Best Use of Gemma 4

> Dual-category eligibility will be confirmed with the event organizers. Evidence for both categories is included below.

---

## Project links

- **Repository:** https://github.com/Saisharathchandranandnetha/SinkProof
- **License:** Apache-2.0 — https://github.com/Saisharathchandranandnetha/SinkProof/blob/main/LICENSE

---

# Problem and solution

## The current problem

Telemetry pipelines have quietly become part of the security boundary.

A modern OpenTelemetry Collector may redact secrets, remove PII, preserve identifiers, filter noise, route security events, and transform attributes before data reaches an external backend.

But the common deployment workflow still looks like:

```text
write YAML → validate config → deploy → inspect production
```

Configuration validation proves that a configuration can load. It does **not** prove that the resulting pipeline preserves the guarantees the team intended.

A configuration can be valid while:

- secrets still reach an external exporter,
- a required request or trace identifier disappears,
- a filter silently drops important records,
- routing sends telemetry to an unintended destination,
- or a negative security test passes only because no telemetry reached the sink.

The gap we are targeting is:

> **Configuration validity is not behavioral proof.**

## The impact we are trying to create

SinkProof introduces a pre-deployment proof step:

```text
Intent
  ↓
Executable Telemetry Contracts
  ↓
Real Collector Execution
  ↓
Deterministic Verification
  ↓
Mutation Testing
  ↓
Evidence
```

Instead of asking:

> "Does this config look correct?"

we ask:

> **"Can this pipeline prove that the expected security and data-integrity properties hold?"**

And then:

> **"Would these tests still detect the problem if the configuration regressed?"**

This creates a path toward telemetry **policy-as-code with executable evidence**.

---

# Approach and technologies

## 1. Telemetry Contract IR

SinkProof defines a small contract language for machine-checkable telemetry invariants.

Current contract types:

- `forbidden_value`
- `must_reach`
- `must_not_reach`
- `preserve_field`

Example:

```yaml
- id: no-secret-canaries
  type: forbidden_value
  sinks: [siem, analytics]
  canaries: [password, token]
  severity: critical

- id: request-id-survives
  type: preserve_field
  sink: analytics
  field:
    scope: log
    key: request.id
  severity: high
```

The goal is to represent *what must be true* independently from the implementation details of the Collector processors.

## 2. Real Collector execution

SinkProof runs the candidate configuration inside a real `otel/opentelemetry-collector-contrib` container.

The harness:

1. starts the Collector,
2. injects synthetic OTLP telemetry,
3. lets the actual processors and routes execute,
4. captures exporter output,
5. evaluates the contracts against that output.

The core verdict path therefore measures runtime behavior rather than only statically parsing YAML.

## 3. Deterministic verification

PASS / FAIL / INCONCLUSIVE decisions are produced by SinkProof code, not by the language model.

The verifier checks:

- forbidden canary values,
- destination reachability,
- forbidden destination reachability,
- field preservation,
- non-vacuity.

This is a deliberate trust boundary:

> **AI proposes. SinkProof verifies.**

## 4. Non-vacuity

A negative assertion such as:

> "No password reached the SIEM"

must not pass simply because no telemetry reached the SIEM.

SinkProof checks whether applicable canary-bearing cases actually exercised the sink before accepting the negative assertion.

## 5. Mutation testing

SinkProof deliberately corrupts a known-good Collector configuration and reruns the contract suite.

Current mutation operators:

- drop processor,
- drop OTTL statement,
- perturb attribute key,
- weaken severity filter.

Each valid mutant is classified as **killed** or **survived**.

```text
Mutation Score = killed / (killed + survived)
```

This provides evidence about the strength of the test suite itself.

## 6. Evidence + static localisation

On failure, SinkProof records:

- contract,
- severity,
- sink,
- case,
- canary/field,
- pipeline path,
- processors related to the affected key.

This turns a failed policy into inspectable evidence rather than a generic alert.

## 7. Gemma 4 multimodal contract compilation

Gemma 4 receives:

- an architecture diagram,
- plain-English requirements,
- and a deterministic inventory of known sinks, keys, and canaries.

It proposes structured contracts.

The output then passes through a schema and allow-list guard before it can enter the verification flow.

## 8. Reproducible record/replay

Model responses may be cached by an input hash so the exact proposal can be replayed during an offline demo. Replayed outputs still pass through the same guard.

---

# What we actually built in the hackathon window

A production telemetry verification platform is much larger than a five-hour build.

We deliberately chose a narrow vertical slice and implemented the core proof loop:

### Built and demonstrated

- Telemetry Contract IR
- real OpenTelemetry Collector execution
- synthetic OTLP log fixtures
- secret / PII-like synthetic canaries
- deterministic PASS / FAIL / INCONCLUSIVE verification
- non-vacuity checks
- routing assertions
- field-preservation assertions
- evidence records
- static fault localisation
- structure-aware mutation testing
- mutation score
- Gemma 4 multimodal contract proposal
- model-output guard
- CLI
- Streamlit demo
- CI workflow
- reproducible example scenario

### Intentionally not claimed as production-ready

- full metrics and traces parity,
- arbitrary enterprise topologies,
- generalized autonomous remediation,
- regulatory compliance certification,
- large-scale benchmark superiority,
- organization-wide policy management.

The goal of the hackathon build was to prove that the verification model works end to end.

---

# Measured evidence from the included scenario

The checkout example is a seeded evaluation scenario.

## Vulnerable pipeline

Using the stronger contract suite:

```text
4 PASS
3 FAIL
0 INCONCLUSIVE
```

The failing contracts expose secret/PII-like leakage and loss of a required request identifier.

## Corrected pipeline

The same suite against the corrected configuration:

```text
7 PASS
0 FAIL
0 INCONCLUSIVE
```

## Mutation adequacy experiment

Weak suite:

```text
1 / 12 mutants killed
Mutation score: 8.3%
```

Stronger suite:

```text
12 / 12 mutants killed
Mutation score: 100%
```

These results are specific to the included seeded scenario. They demonstrate that SinkProof can distinguish a weak contract suite from one that catches the injected regressions. They are not presented as a production benchmark.

---

# Challenge evidence

## Best Open-Source AI Project

### Open-source / open-weight AI component and its role

Open-weight model support is part of the specification layer.

SinkProof includes an Ollama-compatible backend and uses model reasoning to translate human requirements into structured telemetry contracts.

The AI component is central because the difficult human-facing step is turning architecture/security intent into explicit machine-checkable invariants.

The AI does not decide security verdicts.

### Code links

- Gemma / model integration:
  https://github.com/Saisharathchandranandnetha/SinkProof/blob/main/pipewitness/ai/gemma.py
- Model guard:
  https://github.com/Saisharathchandranandnetha/SinkProof/blob/main/pipewitness/ai/guard.py
- Prompts:
  https://github.com/Saisharathchandranandnetha/SinkProof/blob/main/pipewitness/ai/prompts.py

### Agent Skill Open Standard compliance

**Not applicable.**

SinkProof is submitted as an original verification/model harness rather than an Agent Skill.

### Original harness implementation

The original harness contains:

1. Telemetry Contract IR
2. real Collector lifecycle runner
3. deterministic contract verifier
4. non-vacuity logic
5. structure-aware mutation engine
6. mutation adequacy scoring
7. evidence model
8. static fault localisation
9. model-output guard

Core code:

- https://github.com/Saisharathchandranandnetha/SinkProof/blob/main/pipewitness/contracts.py
- https://github.com/Saisharathchandranandnetha/SinkProof/blob/main/pipewitness/runner.py
- https://github.com/Saisharathchandranandnetha/SinkProof/blob/main/pipewitness/verify.py
- https://github.com/Saisharathchandranandnetha/SinkProof/blob/main/pipewitness/mutate.py
- https://github.com/Saisharathchandranandnetha/SinkProof/blob/main/pipewitness/evidence.py
- https://github.com/Saisharathchandranandnetha/SinkProof/blob/main/pipewitness/localize.py

---

## Best Use of Gemma 4

### Model identifier + Gemini API integration

Primary challenge model:

```text
gemma-4-26b-a4b-it
```

The integration is implemented with the Google GenAI SDK in:

https://github.com/Saisharathchandranandnetha/SinkProof/blob/main/pipewitness/ai/gemma.py

### Multimodal input

Gemma 4 receives:

- `examples/checkout/architecture.png`
- `examples/checkout/requirements.txt`
- deterministic inventory generated from the candidate Collector config and fixtures.

### Useful output

The model proposes structured telemetry contracts that are then schema-checked and allow-list constrained.

The useful multimodal step is converting **visual architecture + textual intent** into candidate executable invariants.

The model result is not shown as a chat answer; it becomes input to the verification harness.

---

# Why this is not another observability dashboard

SinkProof does not aim to replace:

- OpenTelemetry Collector,
- telemetry routing platforms,
- observability backends,
- application tracing tools.

It adds a verification layer around the pipeline.

The category we are exploring is:

> **Pre-deployment behavioral verification for telemetry infrastructure.**

Our core contribution is the combination of:

- executable telemetry contracts,
- real-runtime evaluation,
- non-vacuous security assertions,
- structure-aware configuration mutation,
- and deterministic evidence.

---

# Future plan

## Phase 1 — Generalized proof engine

- remove example-specific sink assumptions,
- dynamically derive sinks/exporters,
- pin Collector image versions and digests,
- add trace contracts,
- add metric contracts,
- add more independent topologies,
- expand mutation operators,
- emit structured JSON/SARIF evidence.

## Phase 2 — Verified remediation

The current remediation module is a bounded seeded prototype.

The target design is:

```text
Failure Evidence
      ↓
Gemma Patch Proposal
      ↓
Strict PatchOp Schema
      ↓
Apply in Sandbox
      ↓
otelcol validate
      ↓
Real Collector Run
      ↓
Contract Verification
      ↓
Mutation Verification
      ↓
VERIFIED FIX / REJECTED PATCH
```

The important principle remains the same:

> The model can suggest a patch; it cannot declare the patch correct.

## Phase 3 — CI/CD policy gate

Target usage:

```bash
sinkproof verify \
  --config otel-collector.yaml \
  --contracts telemetry.contracts.yaml
```

Future CI features:

- PR annotations,
- deployment blocking,
- mutation-score thresholds,
- signed evidence bundles,
- SARIF output,
- baseline drift detection.

## Phase 4 — Adversarial telemetry testing

Add property-based and fuzz-generated telemetry:

- nested data,
- encoded secrets,
- malformed values,
- Unicode,
- extreme cardinality,
- type drift,
- partial identifiers,
- false-positive canaries.

This would evolve SinkProof from a fixed fixture runner into an adversarial telemetry verification lab.

## Phase 5 — Cross-engine telemetry contracts

Explore adapters for other programmable telemetry pipelines such as Vector and Fluent Bit.

The long-term idea is that a contract should describe **what must remain true**, while adapters define how that invariant is tested against each engine.

## Phase 6 — Research direction

Potential research areas:

- mutation testing for observability infrastructure,
- executable security contracts for telemetry systems,
- LLM-assisted specification with deterministic runtime verification,
- coverage-guided telemetry mutations,
- differential verification between Collector versions,
- formalization of selected telemetry invariants.

---

# Current status

## What works

- CLI
- Streamlit UI
- real Collector execution
- deterministic contract evaluation
- non-vacuity checks
- mutation testing
- evidence generation
- fault localisation
- multimodal Gemma contract proposal
- model guard
- recorded demo fallback
- CI workflow
- Apache-2.0 licensing

## Known limitations / incomplete features

- primary runtime path currently focuses on logs,
- primary end-to-end demonstration is the seeded checkout topology,
- model-side sink mapping still contains example-specific assumptions,
- remediation is currently a bounded seeded prototype,
- Docker is the main execution backend,
- SinkProof verifies technical properties and does not claim regulatory certification.

We document these limitations because the project itself is built around one principle:

> **Evidence over claims.**

---

# Reproduction

## Install

```bash
git clone https://github.com/Saisharathchandranandnetha/SinkProof.git
cd SinkProof

python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Vulnerable pipeline

```bash
sinkproof verify \
  -c examples/checkout/collector.vulnerable.yaml \
  -k examples/checkout/contracts.yaml \
  -t examples/checkout/telemetry.yaml
```

## Corrected pipeline

```bash
sinkproof verify \
  -c examples/checkout/collector.fixed.yaml \
  -k examples/checkout/contracts.yaml \
  -t examples/checkout/telemetry.yaml
```

## Mutation testing

```bash
sinkproof mutate \
  -c examples/checkout/collector.fixed.yaml \
  -k examples/checkout/contracts.yaml \
  -t examples/checkout/telemetry.yaml
```

## Gemma contract compilation

```bash
sinkproof compile \
  -i examples/checkout/architecture.png \
  -r examples/checkout/requirements.txt \
  -c examples/checkout/collector.fixed.yaml \
  -t examples/checkout/telemetry.yaml \
  -o compiled.yaml
```

## Interactive demo

```bash
streamlit run app.py
```

---

# Final statement

SinkProof is not trying to prove that five hours is enough to build an enterprise observability security platform.

The five-hour build demonstrates a more fundamental idea:

> **Telemetry infrastructure should not be trusted because its configuration looks correct. It should be trusted because its behavior can be tested, challenged, and proven.**

That is the direction SinkProof is built to explore.
