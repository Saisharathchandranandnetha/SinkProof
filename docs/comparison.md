# SinkProof — Competitive Positioning

SinkProof should not be evaluated as another telemetry router, observability backend, or generic AI assistant.

Its target category is:

> **Pre-deployment behavioral verification for telemetry infrastructure.**

The core claim is deliberately narrow:

> **A configuration can be valid without proving that the resulting telemetry behavior satisfies security and data-integrity requirements.**

SinkProof adds executable contracts, real runtime execution, deterministic evidence, and mutation adequacy testing around that gap.

---

## Positioning matrix

| Tool / category | What it primarily does well | Where SinkProof differs |
|---|---|---|
| OpenTelemetry Collector config validation | Confirms Collector config can be parsed/validated | SinkProof evaluates behavioral invariants against a real run |
| OpenTelemetry Collector test infrastructure | Tests Collector components and integration behavior | SinkProof exposes user-defined policy contracts over candidate pipelines |
| Cribl Stream / pipeline tooling | Powerful telemetry processing, transformation, routing, preview | SinkProof focuses on independent contract verification and test adequacy |
| Tracetest | Application/API integration testing using distributed traces | SinkProof focuses on Collector policy behavior and telemetry transformation guarantees |
| Static config analysis | Detects suspicious or invalid patterns without execution | SinkProof uses the actual Collector runtime for the verdict path |
| Generic LLM assistant | Explains or suggests configuration | SinkProof constrains AI to specification/proposal; deterministic execution decides |
| **SinkProof** | **Executable telemetry policy verification** | **Contracts + real runtime + non-vacuity + mutation testing + evidence** |

This table is a positioning summary, not a claim that the products above have zero feature overlap.

---

# The exact gap SinkProof targets

Existing tooling can validate configuration, route and transform telemetry, preview sample transformations, and test applications with telemetry.

The gap SinkProof explores is:

> **Teams lack a lightweight, developer-facing way to express telemetry guarantees as executable contracts, prove those guarantees against a real candidate Collector configuration, and then mutation-test those contracts to measure whether they can detect regressions.**

That is the product thesis.

---

# Why mutation testing matters

A passing test suite can still provide false confidence.

Example:

```text
Requirement:
Passwords must never reach the SIEM.

Test:
No password appears in captured SIEM output.

Result:
PASS
```

But this can be meaningless if:

- no test record reached the SIEM,
- the fixture did not contain a password,
- the path containing the redaction rule was never exercised,
- the assertion only covered the happy path.

SinkProof attacks this from two directions:

1. **non-vacuity** — make sure the relevant path/case was actually exercised;
2. **mutation testing** — deliberately break the pipeline and verify that the contracts fail.

That is the distinction between:

> "the test passed"

and

> **"the test demonstrated sensitivity to the kind of regression we care about."**

---

# Why the real Collector matters

SinkProof could have implemented a YAML simulator.

We intentionally avoided making simulation the final verdict path.

OpenTelemetry Collector processors and routing have runtime semantics. Running a real Collector provides stronger evidence that the observed output reflects the actual engine rather than our reimplementation of it.

The tradeoff is increased runtime cost and Docker dependency, which we document openly.

---

# Why AI is useful but not authoritative

AI is valuable for turning ambiguous human intent into structured candidate contracts.

For example:

```text
"Passwords and tokens must never leave the collector,
request IDs must survive,
and all ERROR events must reach security."
```

becomes candidate machine-checkable invariants.

But using the model itself to decide whether the pipeline is safe would create a trust problem.

So SinkProof defines a strict boundary:

```text
Human intent / diagram
        ↓
      Gemma 4
        ↓
Candidate Contract IR
        ↓
Schema + Inventory Guard
        ↓
Real Collector Execution
        ↓
Deterministic Verifier
        ↓
Evidence
```

The model provides semantic assistance.

The runtime provides proof.

---

# What SinkProof does not claim

To keep the submission technically defensible, SinkProof does **not** claim that:

- no other telemetry tool performs testing,
- no existing platform can preview or inspect transformed telemetry,
- the current hackathon build is production-ready,
- 100% mutation score on the seeded example means 100% real-world protection,
- passing SinkProof contracts makes a company PCI/HIPAA/GDPR compliant,
- the current remediation module is a general autonomous repair agent.

The current evidence supports a narrower claim:

> **SinkProof demonstrates an executable-contract + mutation-testing approach for detecting seeded telemetry security and data-integrity regressions in a real OpenTelemetry Collector pipeline.**

That is enough for a serious hackathon prototype.

---

# Why this can become larger

The Contract IR can potentially outlive the specific Collector implementation.

Long-term:

```text
                  Telemetry Contract
                        │
          ┌─────────────┼─────────────┐
          ↓             ↓             ↓
        OTel          Vector       Fluent Bit
       adapter        adapter        adapter
          │             │             │
          └─────────────┴─────────────┘
                        ↓
                Verification Evidence
```

If that direction proves useful, SinkProof becomes less about "testing a YAML file" and more about:

> **portable behavioral guarantees for telemetry infrastructure.**

---

# One-line competitive statement

> **Routing tools move telemetry. Testing tools inspect systems. SinkProof is trying to prove that the telemetry pipeline itself preserves the guarantees engineers depend on.**
