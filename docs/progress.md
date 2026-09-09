# Portfolio milestone status

Latest update: 2026-09-07. This tracks deliverables, not a claim that a production healthcare agent is complete.

## Zero-cost evaluation and error handling — 2026-09-07

- Added 20 offline engineering challenges alongside the six original smoke cases: 15 met their
  expectations and 5 exposed documented limitations (75%, not clinical accuracy).
- Added a guaranteed-offline API/UI evaluation action, `make offline-eval`, and `make api-offline`.
- Added sanitized provider error categories and actionable CLI/UI messages; no automatic retry.
- All 94 automated tests and lint passed. Test runs block outbound socket connections.
- A prior user-initiated real-model request was rejected with `RateLimitError` at the first planner
  call. No usable model output was received. The user reported $0 API credits and chose not to
  recharge. This iteration made no model calls or billing changes.

See [saved challenge results](../reports/offline-20260907T235426Z/README.md) and
[methodology and diagnostics](offline-evaluation.md). Existing failure reports are preserved.

## Earlier core-upgrade snapshot — 2026-09-07

Optional adaptive orchestration is implemented: bounded model-selected retrieval, semantic
verification with quote checks, one repair/recheck, explicit abstention and preserved draft audit.
English UI and evaluation exports reflect both initial and final candidate outcomes.
57 automated tests pass (35 new scripted adaptive/integration tests); lint passes.
At that point, the comparison preview found no model/key in the agent's shell and no provider
request had been made by the agent. The subsequent user-initiated attempt is recorded above.
No independent clinical benchmark was added, and the existing
video/Docker report remain the September 5 offline artifacts. See [adaptive core](adaptive-agent.md).

## Earlier milestone snapshot — 2026-09-05

| Original milestone | Current evidence | Remaining work |
| --- | --- | --- |
| 1. Repository, problem, architecture | Local project structure, README problem statement, architecture diagram in workbench.md | Review and publish the repository to GitHub; no publication performed in this iteration |
| 2. Agent + RAG + evaluator | BM25 retrieval, extractive reasoner, citation checks, conflict flags, FastAPI, six-case evaluator; optional model adapter has mocked tests | Configure and test a real model, collect an independent evaluation set, measure actual model quality and cost |
| 3. UI, README, results, two-minute video | Complete locally: English UI, screenshot README, saved baseline report, 120-second narrated/subtitled MP4, verified Docker startup | Review the video and publish approved repository/video artifacts; no public upload performed |
| 4. FDE / Agent resume | Technical project can be described as an offline prototype | Write evidence-backed resume bullets after the release scope is agreed |
| 5. Company applications | No application work performed in this project iteration | Select roles and submit applications with user authorization |

## What the current demo proves

The pipeline can retrieve attributed evidence, produce structured citation-bound statements,
identify fixed verification failures, abstain on an unrelated input, and export measured results.
The UI is connected to these functions rather than being a static mockup.

## Step 3 deliverables

- [README](../README.md), including a screenshot and measured baseline summary.
- [Saved results](../reports/baseline-2026-09-05/README.md) and the companion raw JSON.
- [Demo guide](demo.md); local MP4 at `artifacts/medagent-demo/medagent-demo.mp4`.
- [Docker verification](deployment-check.md): API and UI both healthy, full browser flow passed.
- 22 automated tests passed, plus isolated-browser walkthroughs against native and Docker services.

The temporary `medagent-step3` containers/network were removed after verification. Built images
remain available; original development servers were not stopped.

## What it does not yet prove

Clinical accuracy, general medical coverage, a validated hallucination rate, a robust semantic
verifier, autonomous multi-LLM collaboration, or production deployment readiness. Six curated
smoke cases and deliberate injected errors are not independent model-quality benchmarks.

## Next release gate

1. Approve the English workflow and its limited respiratory/privacy evidence-review scope.
2. Run the optional reasoner with a real model, without committing API credentials.
3. Add independently labeled cases including valid paraphrases, contradictions, distractors,
   insufficient evidence, and out-of-scope requests; compare baseline and model modes.
4. The local Docker check, dated offline report, and two-minute demo are ready. Review them
   and publish the approved repository/video; add model comparison results when available.
5. Turn the verified results into resume bullets and application material.
