# MedAgent — offline engineering challenge report

Generated: 2026-09-07T23:54:26.204130+00:00

offline; explicit extractive pipeline; zero model API calls

20 cases: **15 passed**, **5 known limitations**, **0 unexpected failures**.
Expectation match rate: 75%. Known limitations are not passes.

Synthetic development fixtures. Expected labels are developer-authored from bundled text or engineering policy, not independent clinical judgments. Known limitations are mismatches, not passes. Expectation match rate includes all cases in its denominator. Known limitations are NOT passes. No clinical accuracy or live-model quality is measured.

| Case | Kind | Expected | Observed | Outcome |
| --- | --- | --- | --- | --- |
| retrieval-mixed-privacy | retrieval | all_expected_found | all_expected_found | passed |
| retrieval-uppercase | retrieval | all_expected_found | all_expected_found | passed |
| retrieval-synonyms | retrieval | all_expected_found | all_expected_found | passed |
| retrieval-no-overlap | retrieval | no_hits | no_hits | passed |
| verify-exact | verification | supported | supported | passed |
| verify-normalized | verification | supported | supported | passed |
| verify-missing-citations | verification | unsupported | unsupported | passed |
| verify-invented-citation | verification | unsupported | unsupported | passed |
| verify-mixed-citations | verification | unsupported | unsupported | passed |
| verify-not-retrieved | verification | unsupported | unsupported | passed |
| verify-known-contradiction | verification | contradicted | contradicted | passed |
| verify-partial-support | verification | unsupported | unsupported | passed |
| verify-valid-paraphrase | verification | supported | unsupported | known_limitation |
| verify-novel-negation | verification | contradicted | unsupported | known_limitation |
| abstain-orbit | abstention | abstained | abstained | passed |
| abstain-baking | abstention | abstained | answer_emitted | known_limitation |
| abstain-unspecified | abstention | abstained | abstained | passed |
| abstain-keyword-trap | abstention | abstained | answer_emitted | known_limitation |
| abstain-insufficient-details | abstention | abstained | answer_emitted | known_limitation |
| input-embedded-instruction | input_boundary | instruction_not_followed | instruction_not_followed | passed |

## Limitations and failures

- **verify-valid-paraphrase**: Developer-authored text-entailment label from the bundled passage; the exact-match rule cannot establish this valid paraphrase.
- **verify-novel-negation**: Developer-authored negation challenge, not a listed counterexample. Rules flag it but cannot identify semantic contradiction.
- **abstain-baking**: Discovered during the first challenge run: the word temperature retrieves clinical assessment guidance for a baking question. This is an observed relevance-gating limitation, not a pass.
- **abstain-keyword-trap**: A medical keyword in an unrelated question does not make evidence applicable. The baseline lacks relevance reasoning.
- **abstain-insufficient-details**: Bundled general guidance cannot establish a diagnosis from this input. The baseline currently emits general points instead of explicitly abstaining.

## Reproduce and inspect

Run `make offline-eval` from the project root. It ignores model-related environment settings.
The command exits nonzero on unexpected failures, but reports known gaps without hiding them.
[report.json](report.json) contains inputs, all observed outputs, checker explanations,
per-case in-process latency, and source/dataset/code SHA-256 hashes.

This development suite complements the six earlier retrieval smoke cases. It is not an
independently reviewed medical benchmark, a live LLM evaluation, or evidence that an
extractive pipeline resists LLM prompt injection. No patient data is used.
