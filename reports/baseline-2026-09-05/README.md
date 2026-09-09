# MedAgent — offline baseline results

Generated: 2026-09-06T00:38:50.647690+00:00

**Scope:** Six curated synthetic smoke cases, not an independent clinical benchmark.
The extractive reasoner copies curated review points; perfect text matching is expected.
These results do not establish medical accuracy or a real-model hallucination rate.

| Metric | Observed value |
| --- | --- |
| Retrieval Recall@K (K=1) | 100% |
| Expected citation-ID precision | 100% |
| Rule text-match rate | 100% |
| Cases with review flags | 0% |
| Mean pipeline latency | 0.062 ms |
| P95 pipeline latency | 0.125 ms |
| Model API cost | $0.00 — no model calls |
| Clinical accuracy / independent hallucination rate | Not measured |

Latency is a single in-process run over a six-chunk in-memory corpus. It excludes
startup, network, browser rendering, and model latency. P95 uses the nearest-rank method
(the slowest case at this sample size). Values vary by machine and run.

## Per-case results

| Case | Recall@1 | Citation precision | Text match | Flags | Latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| eval-urgent-001 | 100% | 100% | 100% | 0 | 0.125 |
| eval-antibiotic-001 | 100% | 100% | 100% | 0 | 0.062 |
| eval-assessment-001 | 100% | 100% | 100% | 0 | 0.051 |
| eval-risk-001 | 100% | 100% | 100% | 0 | 0.050 |
| eval-privacy-001 | 100% | 100% | 100% | 0 | 0.042 |
| eval-deidentification-001 | 100% | 100% | 100% | 0 | 0.040 |

## Separate behavior checks

- injected_errors_detected: PASS
- unrelated_input_abstains: PASS

The error fixture deliberately injects two errors. Detecting them is not a
measurement of natural model failures. The unrelated-input check is not a clinical
out-of-distribution benchmark.

## Reproduce

Run `make report` from the repository root. It always uses the
offline reasoner, even if the shell is configured for a model provider.

See [report.json](report.json) for inputs, outputs, source/code SHA-256 hashes,
runtime metadata, and full per-case measurements.
