# Zero-cost evaluation and actionable errors

Implemented 2026-09-07. The user chose not to add API credits; this iteration made no model calls.
All model/error-path tests use scripted responses or locally constructed SDK exceptions.

## Run without an API key

```bash
cd /Users/yanglyu/Documents/ChatGPT/agent
make offline-eval
```

No server is needed. The runner constructs the extractive baseline explicitly, ignores model-mode
environment variables, and uses the bundled corpus and challenge data. It writes a new timestamped
folder under `reports/`; existing reports are never overwritten.

To use the English UI, start `make api-offline` in one terminal and `make ui` in another. If an old
server occupies the port, stop only that server in its own terminal with Ctrl+C before restarting.
In **Evaluate**, choose **Run Offline Checks**. This calls `POST /v1/evaluations/offline`, which is
separate from the original six-case active-mode evaluation endpoint. The offline action cannot
select the active model. The original model-enabled actions are still opt-in and can be billable.

## What the 20 challenges measure

The new fixtures supplement rather than replace the six original retrieval smoke cases.

| Check group | Count | Matched | Unmet |
| --- | ---: | ---: | ---: |
| Retrieval: multiple sources, capitalization, curated synonyms, no overlap | 4 | 4 | 0 |
| Verification: exact text, citations, compound claims, paraphrase and negation | 10 | 8 | 2 |
| Abstention: absent details, unrelated domains, misleading keywords | 5 | 2 | 3 |
| Untrusted input: embedded marker must not enter generated claims | 1 | 1 | 0 |
| Total | 20 | 15 | 5 |

Saved observation: [report and raw JSON](../reports/offline-20260907T235426Z/README.md).

**15/20 (75%) is a development expectation-match rate, not clinical accuracy.** Labels were
authored during development using bundled text and intended engineering behavior; they were not
independently reviewed by clinicians. Exact-match checks naturally pass copied evidence. The
input-boundary check applies only to the extractive pipeline and does not test a real LLM's
prompt-injection resistance. Latencies are in-process observations, not live-model latencies.

The report counts `passed`, `known_limitation` and `failed` separately. Both latter outcomes count
as unmet expectations. Only a known limitation explicitly declared in the fixture can receive that
label; a new mismatch is an unexpected failure and makes the CLI exit nonzero. Existing known
limitations do not fail CI, but remain prominent in the score, case table, and raw output.

### Five observed limitations

1. A valid paraphrase is conservatively marked unsupported by exact-text rules.
2. A novel negation is flagged unsupported, but rules cannot label it as a semantic contradiction.
3. A rocket named "Bronchitis" retrieves irrelevant respiratory review points.
4. A baking question containing "temperature" retrieves clinical assessment guidance. This was
   discovered in the first suite run and recorded as a keyword-relevance limitation, not a pass.
5. A diagnostic question with insufficient case details receives general review points instead
   of explicit abstention. Those points are not a diagnosis, but still fail the target behavior.

These gaps were not patched with case-specific keyword exceptions. Relevance and entailment need
separate validation. The optional semantic pipeline has scripted tests but has not yet produced
a successful live model evaluation. No improvement percentage is claimed for it.

## Provider diagnostics

The prior user's first live attempt received `RateLimitError` and stopped at the planner. Its
existing report recorded only `provider_error`, so the precise subtype cannot be recovered from
that file. The user then reported a $0 API balance and chose not to recharge. The original failure
record is preserved unchanged; no retry was performed during this iteration.

Future failures include a sanitized `failure` object in adaptive responses; single-pass model
failures return the same object in HTTP 502 `detail`. The CLI, UI and traces surface it.

| Signal | Category | Behavior |
| --- | --- | --- |
| `credit_balance_exhausted` | credits_exhausted | Explain missing prepaid credits; offer offline mode |
| `insufficient_quota` code/type | quota_exceeded | Inspect credits/limits; no repeated retry |
| Organization/project spend-limit code | spend_limit | Inspect the applicable limit; never change it automatically |
| Organization usage-limit code | usage_limit | Inspect provider-assigned limits |
| `rate_limit_exceeded`, `slow_down`, or `rate_limit_error` type | rate_limited | Display safe Retry-After value; manual retry only |
| Unclassified 429 | rate_limit_or_quota | Do not assume that paying or waiting will fix it |
| SDK timeout / connection error | timeout / connection | Distinct connectivity guidance; no automatic retry |
| 401 / 403 / 404 | authentication / permission / model_unavailable | Configuration/access guidance; no model substitution |
| 400, 422 / 5xx | invalid_request / service_unavailable | Distinguish malformed requests from provider failures |

Only allowlisted error codes, validated status/request IDs and finite numeric Retry-After values
are exported. Exception messages, request headers, response bodies and arbitrary provider fields
are never included. A missing/unknown code stays null. `retryable` describes a potentially
transient condition, not an instruction to automatically retry; retries remain disabled.
Missing token usage remains partial/unavailable and does not establish zero cost for failed calls.

Classification follows the [official OpenAI error-code guidance](https://developers.openai.com/api/docs/guides/error-codes).
In particular, a 429 does not uniquely identify request-frequency throttling.

## Verification performed

- **94 automated tests passed**, including existing baseline/adaptive regressions and new SDK-error,
  CLI/API/UI, secret-redaction, offline-isolation, report-preservation and negative-case checks.
- Tests force the baseline mode at collection and block socket connections. In-process FastAPI
  and mocked transports remain available; real model access is not needed.
- `ruff check .` passed.
- Offline report generated with source, dataset and application-code hashes plus raw observations.
- Two existing dependency deprecation warnings remain; tests do not suppress them.
- No Docker rerun, new video recording, account changes, public upload, or live model retry.

Next engineering target: evaluate question relevance and abstention using these same unmet cases,
while keeping development labels separate from future independent quality evaluation.
