# DECISIONS.md

Log of decisions made when the real Collector or API disagrees with the spec or environment constraints.

## 1. Pinned Collector Image: `otel/opentelemetry-collector-contrib:latest` (v0.162.0)
- **Context:** The spec proposed `0.116.0`. On Linux/x86_64 runc environment, 0.116.0 distroless failed with `exec /otelcol-contrib: no such file or directory` due to dynamic linker/glibc dependencies in older distroless image.
- **Decision:** Pinned `otel/opentelemetry-collector-contrib:latest` (0.162.0, digest `sha256:39923a8e431bd1f57be82411999d389fcfe40857492e4365456d97a4c1f74be6`).
- **Validation:** Both `collector.vulnerable.yaml` and `collector.fixed.yaml` passed `validate --config=...` with exit code 0 on this image.
