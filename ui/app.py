from __future__ import annotations

import html
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
EXAMPLES = {
    "Respiratory assessment": (
        "Synthetic adult case has a cough, colored sputum, and possible acute bronchitis.",
        "Which findings should a clinician assess when considering pneumonia?",
    ),
    "Urgent warning signs": (
        "Synthetic adult case reports difficulty breathing and persistent chest pain today.",
        "Which issue should be handled first?",
    ),
    "Higher-risk history": (
        "Synthetic respiratory illness case involves an older adult with kidney disease and diabetes.",
        "Do these higher-risk features change the urgency of professional review?",
    ),
    "Privacy & identifiers": (
        "A synthetic case submission includes a name, home address, birth date, and medical record number.",
        "What information should be removed before the case is submitted?",
    ),
    "Out-of-scope question": (
        "Orbital mechanics and telescope mirrors aboard a spacecraft.",
        "Which launch trajectory is most efficient?",
    ),
    "Custom synthetic case": ("", ""),
}
STEPS = [
    ("retriever", "Retriever", "Finds relevant evidence with BM25."),
    ("reasoner", "Reasoner", "Produces citation-bound review points."),
    ("verifier", "Verifier", "Checks exact text and known counterexamples."),
    ("conflict_detector", "Conflict Detector", "Flags statements needing human review."),
]
LABELS = {
    "supported": "Text match passed",
    "unsupported": "Support not established",
    "contradicted": "Known counterexample matched",
}


def load_example() -> None:
    summary, question = EXAMPLES[st.session_state.example]
    st.session_state.case_summary = summary
    st.session_state.review_question = question
    st.session_state.pop("active_review", None)


def new_case() -> None:
    st.session_state.example = "Custom synthetic case"
    st.session_state.case_id = "interactive-demo"
    load_example()


def restore_review(entry: dict) -> None:
    submitted = entry["input"]
    if "patient_summary" in submitted:
        st.session_state.example = "Custom synthetic case"
        st.session_state.case_summary = submitted["patient_summary"]
        st.session_state.review_question = submitted["question"]
        st.session_state.case_id = submitted["case_id"]
        st.session_state.top_k = submitted["top_k"]
    st.session_state.active_review = entry


def post(path: str, payload: dict | None = None) -> dict:
    timeout = 600 if path == "/v1/evaluations/run" else 120
    response = httpx.post(f"{API_BASE_URL}{path}", json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def render_failure(failure: dict) -> None:
    st.error("Run stopped safely · " + failure.get("message", "Provider request failed."))
    st.caption(failure.get("suggested_action", "Inspect the backend before retrying."))
    if failure.get("retry_after_seconds") is not None:
        st.caption(f"Provider Retry-After: {failure['retry_after_seconds']} seconds · No automatic retry")
    with st.expander("Safe error diagnostics"):
        st.json({key: failure.get(key) for key in (
            "category", "code", "http_status", "request_id", "retryable", "retry_after_seconds",
        )})


def render_request_error(exc: Exception) -> None:
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            detail = exc.response.json().get("detail")
        except (ValueError, AttributeError):
            detail = None
        if isinstance(detail, dict) and "category" in detail and "suggested_action" in detail:
            render_failure(detail)
            return
    if isinstance(exc, httpx.TimeoutException):
        st.error("The backend request timed out. It may still be running; inspect the API before retrying.")
    else:
        st.error("The request could not be completed. Check your input and backend connection.")


def save_review(result: dict, submitted: dict) -> None:
    entry = {
        "result": result,
        "input": submitted,
        "time": datetime.now(UTC).strftime("%H:%M:%S UTC"),
    }
    st.session_state.active_review = entry
    st.session_state.history = [entry, *st.session_state.get("history", [])][:5]


def run_review(payload: dict | None = None) -> None:
    st.session_state.pop("active_review", None)
    try:
        with st.spinner("Retrieving evidence, drafting claims, and checking support…"):
            result = post("/v1/reviews", payload) if payload else post("/v1/demos/conflict")
            save_review(
                result, payload or {"fixture": "fixed-conflict-demo", "fault_injection": True}
            )
        st.rerun()
    except (httpx.HTTPError, ValueError) as exc:
        render_request_error(exc)


def render_status(result: dict) -> None:
    if result.get("is_demo"):
        st.warning(
            "FAULT-INJECTION DEMO · Two deliberate errors were added for testing, not clinical use."
        )
    adaptive = result["metrics"].get("pipeline_mode") == "adaptive"
    if result["status"] in {"model_error", "budget_exhausted"}:
        if result.get("failure"):
            render_failure(result["failure"])
        else:
            st.error("Run stopped safely · No answer released. " + result.get("stop_reason", ""))
    elif result["status"] == "needs_clarification":
        st.info("More synthetic case information is needed before drafting.")
    elif result["conflicts"]:
        st.error(f"Human review required · {len(result['conflicts'])} flagged statements")
    elif result["status"] == "no_evidence":
        st.info("No matching evidence. The system abstained instead of generating an answer.")
    elif result["status"] == "abstained":
        st.info("Evidence was found, but the reasoner abstained. Review the uncertainty notes.")
    elif adaptive:
        st.success(
            "Repaired and rechecked · Model-assessed evidence support, not clinical validation."
            if result["status"] == "repaired"
            else "Model support checks passed · Clinical correctness is not established."
        )
    else:
        st.success("Text checks passed · Clinical applicability has not been assessed.")


def render_claims(result: dict, only_conflicts: bool = False) -> None:
    labels = LABELS if result["metrics"].get("pipeline_mode") != "adaptive" else {
        "supported": "Model-assessed support · Quote check passed",
        "unsupported": "Support not established · Withheld",
        "contradicted": "Evidence conflict · Withheld",
    }
    verification = {item["claim_id"]: item for item in result["verification"]}
    conflicts = {item["claim_id"]: item for item in result["conflicts"]}
    for claim in result["claims"]:
        if only_conflicts and claim["claim_id"] not in conflicts:
            continue
        check = verification[claim["claim_id"]]
        with st.container(border=True):
            if claim["claim_id"] in conflicts:
                st.error(labels[check["label"]])
                st.caption(
                    "Deliberately injected error"
                    if claim["claim_id"].startswith("injected-")
                    else "Human review required"
                )
            else:
                st.caption(labels[check["label"]])
            st.text(claim["text"])
            st.caption("Sources: " + ", ".join(claim["citation_ids"]))
            if check.get("evidence_quotes"):
                with st.expander("Inspect supporting text"):
                    for quote in check["evidence_quotes"]:
                        st.text(quote["quote"])
                        st.caption(quote["citation_id"])
            if only_conflicts:
                st.caption(check["rationale"])
                st.caption(f"Severity: {conflicts[claim['claim_id']]['severity']}")


def render_answer(entry: dict | None) -> None:
    answer, outputs, conflicts_tab = st.tabs(["Final Answer", "Agent Outputs", "Conflict Analysis"])
    if not entry:
        with answer:
            st.markdown("### Your evidence review starts here")
            st.write(
                "Select a synthetic case and run the agents. Review points will appear here, with supporting sources on the right."
            )
            st.caption("No pre-generated answer. No simulated performance scores.")
        with outputs:
            st.info("Component outputs appear after a run.")
        with conflicts_tab:
            st.info("Run a case, or use the fault-injection demo in Playground.")
        return
    result = entry["result"]
    with answer:
        render_status(result)
        st.markdown("### Evidence review points")
        if not result["claims"]:
            st.caption("No review points released. Candidate drafts, if any, remain in Agent Outputs.")
        render_claims(result)
        if result.get("clarification_questions"):
            st.markdown("#### Information to clarify")
            for question in result["clarification_questions"]:
                st.text(question)
            st.caption("Update the synthetic case above and rerun. No real patient data.")
        with st.expander("Case summary & uncertainty", expanded=True):
            st.text(result["summary"])
            for uncertainty in result["uncertainties"]:
                st.text(uncertainty)
        st.caption(
            f"Completed {entry['time']} · {result['case_id']} · {result['metrics']['reasoner_mode']}"
        )
        st.download_button(
            "Download review JSON",
            json.dumps(entry, indent=2),
            "evidence-review.json",
            "application/json",
        )
    with outputs:
        st.caption(
            "Recorded component outputs, not hidden model reasoning or a live execution stream."
        )
        for step in result["trace"]:
            with st.expander(
                f"{step['component']} · {step['status']} · {step['duration_ms']:.2f} ms"
            ):
                st.json(step["details"])
        for attempt in result.get("attempts", []):
            with st.expander(f"Draft attempt {attempt['attempt']} · {len(attempt['conflicts'])} flags"):
                st.caption("Audit only. Drafts may contain errors and are not final review points.")
                st.json(attempt)
        with st.expander("Input snapshot & full response"):
            st.json(entry)
    with conflicts_tab:
        st.markdown("### Claim-level review flags")
        if result.get("attempts"):
            st.caption(
                "Reasoner–verifier disagreements across all attempts, including repaired errors. "
                "Model judgments are not independent clinical validation."
            )
            for attempt in result["attempts"]:
                st.markdown(f"**Attempt {attempt['attempt']}**")
                if attempt["conflicts"]:
                    render_claims({**result, **attempt}, only_conflicts=True)
                else:
                    st.caption("No flags in this attempt. Inspect verification status in Agent Outputs.")
        else:
            st.caption(
            "These are rule-check disagreements, not independently measured disagreement between autonomous LLM agents."
            )
            if result["conflicts"]:
                render_claims(result, only_conflicts=True)
            elif not result["claims"]:
                st.info("No claims to check. Absence of flags does not establish correctness.")
            else:
                st.success("No rule-check conflicts detected. Clinical correctness is not established.")


def render_sources(result: dict | None) -> None:
    citations = result.get("retrieved_citations", result["citations"]) if result else []
    with st.container(border=True, key="sources_panel"):
        st.markdown(f"### Sources ({len(citations)})")
        st.caption("Curated CDC / HHS paraphrases · Open a source to inspect its evidence.")
        if not result:
            st.info("Sources will appear after retrieval.")
        elif not citations:
            st.info("No matching sources found.")
        cited = {item["citation_id"] for item in result["citations"]} if result else set()
        for index, citation in enumerate(citations, 1):
            with st.expander(f"{index}. {citation['title']}"):
                st.caption(
                    "Cited in output"
                    if citation["citation_id"] in cited
                    else "Retrieved · not cited"
                )
                st.text(citation["excerpt"])
                st.caption("Curator-written review point")
                st.text(citation.get("review_point", ""))
                st.caption(f"{citation['publisher']} · {citation['citation_id']}")
                st.caption(
                    f"Source date {citation['source_updated_at']} · Accessed {citation['source_accessed_at']} · BM25 {citation['retrieval_score']:.2f}"
                )
                st.link_button("Open official source ↗", citation["source_url"])


def render_workflow(result: dict | None) -> None:
    if result and result["metrics"].get("pipeline_mode") == "adaptive":
        with st.container(border=True, key="workflow_panel"):
            st.markdown("### Agent Workflow")
            st.caption("Recorded actions · Bounded adaptive controller, not a live stream.")
            for index, step in enumerate(result["trace"], 1):
                detail = step["details"].get("action", step["status"])
                st.text(f"{index}. {step['component'].title()} · {detail} · {step['duration_ms']:.1f} ms")
            st.caption("Stop reason: " + str(result.get("stop_reason")))
        return
    trace = {step["component"]: step for step in result["trace"]} if result else {}
    rows = []
    for number, (key, name, purpose) in enumerate(STEPS, 1):
        step = trace.get(key)
        state = (
            "pending" if step is None else ("flagged" if step["status"] == "flagged" else "done")
        )
        duration = f"{step['duration_ms']:.2f} ms" if step else "Ready"
        detail = "Waiting for a run"
        if result:
            detail = {
                "retriever": f"{result['metrics']['retrieved_chunks']} evidence chunks retrieved",
                "reasoner": f"{len(result['claims'])} candidate statements",
                "verifier": f"{sum(v['label'] == 'supported' for v in result['verification'])} / {len(result['claims'])} text matches",
                "conflict_detector": f"{len(result['conflicts'])} review flags",
            }[key]
        rows.append(
            f'<div class="workflow-step {state}"><div class="step-number">{number}</div><div class="step-copy"><div class="step-title">{html.escape(name)}<span>{duration}</span></div><p>{purpose}</p><small>{detail}</small></div></div>'
        )
    with st.container(border=True, key="workflow_panel"):
        st.markdown("### Agent Workflow")
        st.markdown('<div class="workflow">' + "".join(rows) + "</div>", unsafe_allow_html=True)
        st.caption("Completed-run timings. Four pipeline roles; not four autonomous model agents.")


def render_metrics(result: dict | None) -> None:
    with st.container(border=True, key="metrics_panel"):
        st.markdown("### Run Metrics")
        metrics = result["metrics"] if result else None
        has_claims = result is not None and bool(result["verification"])
        adaptive = metrics and metrics.get("pipeline_mode") == "adaptive"
        cols = st.columns(2)
        cols[0].metric(
            "Final candidate support" if adaptive else "Text-match rate",
            f"{metrics['supported_claim_rate']:.0%}" if has_claims else "—"
        )
        cols[1].metric("Flagged claims", str(len(result["conflicts"])) if result else "—")
        cols = st.columns(2)
        cols[0].metric("Pipeline latency", f"{metrics['total_ms']:.2f} ms" if metrics else "—")
        offline = metrics and metrics["reasoner_mode"] in {"extractive", "fault_injection_demo"}
        cols[1].metric("Model API cost", "$0.00" if offline else "Not priced" if metrics else "—")
        if offline:
            st.caption("Offline run · No model API call. Latency excludes browser/network time.")
        elif metrics:
            st.caption("Cost requires a model price configuration; no estimate is fabricated.")
            if metrics["token_count_source"] == "provider":
                st.caption(
                    f"Provider tokens: {metrics['input_tokens']} input / {metrics['output_tokens']} output"
                )
            elif adaptive:
                st.caption("Token usage is partial or unavailable; missing usage is not zero cost.")
        if adaptive:
            st.caption(
                f"{metrics['model_calls']} model calls · {metrics['search_calls']} searches · "
                f"{metrics['repair_attempts']} repairs · {metrics['withheld_claims']} final candidates withheld"
            )
            initial = metrics.get("initial_supported_claim_rate")
            if initial is not None:
                st.caption(f"Initial candidate support: {initial:.0%} · Before any repair")
        st.caption(
            "Support checks are not clinical accuracy. An independent hallucination rate has not been measured."
        )


st.set_page_config(page_title="MedAgent | Evidence Review", page_icon="✚", layout="wide")
st.markdown(
    f"<style>{Path(__file__).with_name('styles.css').read_text()}</style>", unsafe_allow_html=True
)

try:
    health = httpx.get(f"{API_BASE_URL}/health", timeout=3)
    health.raise_for_status()
    service = health.json()
except (httpx.HTTPError, ValueError):
    service = None

# Migrate an older UI selection without discarding saved run history.
if st.session_state.get("example") not in EXAMPLES:
    st.session_state.example = next(iter(EXAMPLES))
    load_example()
if "case_summary" not in st.session_state:
    load_example()

with st.sidebar:
    st.markdown('<div class="library-label">CASE LIBRARY</div>', unsafe_allow_html=True)
    st.button("＋ New Case", type="primary", use_container_width=True, on_click=new_case)
    st.radio("Example cases", list(EXAMPLES), key="example", on_change=load_example)
    st.divider()
    st.markdown("**My recent runs**")
    recent = st.session_state.get("history", [])
    if not recent:
        st.caption("No saved runs in this session.")
    for index, item in enumerate(recent):
        st.button(
            f"{item['result']['case_id']} · {item['time']}",
            key=f"restore-{index}",
            use_container_width=True,
            on_click=restore_review,
            args=(item,),
        )
    st.caption("Last 5 runs · session only. Full records are available in Cases.")
    st.divider()
    st.info("Research prototype. Synthetic cases only. Not for diagnosis or patient care.")

brand, connection = st.columns([3, 1], vertical_alignment="center")
with brand:
    st.markdown(
        '<div class="brand"><span class="brand-mark">✚</span><div><h1>MedAgent</h1><p>Multi-Agent Evidence Review</p></div></div>',
        unsafe_allow_html=True,
    )
with connection:
    if service:
        st.markdown('<div class="connection">● Backend connected</div>', unsafe_allow_html=True)
        st.caption(
            f"Mode: {service.get('pipeline_mode', 'baseline')} / {service['reasoner_mode']} · {service['knowledge_documents']} evidence chunks"
        )
    else:
        st.error("Backend unavailable")
        st.caption("Start the API from the project folder: REASONER_MODE=extractive make api")

ask, evaluate, cases, playground, about = st.tabs(
    ["Ask", "Evaluate", "Cases", "Playground", "About"]
)

with ask:
    main, context = st.columns([1.7, 1], gap="medium")
    entry = st.session_state.get("active_review")
    with main, st.container(border=True, key="review_panel"):
        title, clear = st.columns([4, 1], vertical_alignment="center")
        with title:
            st.subheader("Case: " + st.session_state.example)
        with clear:
            st.button("Clear", on_click=new_case, use_container_width=True)
        st.caption(
            "Ask an evidence-review question or describe a synthetic case. The pipeline retrieves, drafts, checks, and flags unsupported statements."
        )
        with st.form("review-form"):
            st.text_area(
                "Synthetic case information",
                key="case_summary",
                height=125,
                max_chars=4000,
                placeholder="Use synthetic information only. Do not enter real patient data.",
            )
            st.text_input("Review question", key="review_question", max_chars=1000)
            settings, action = st.columns([1, 1], vertical_alignment="bottom")
            with settings:
                st.selectbox("Evidence chunks", list(range(1, 7)), index=1, key="top_k")
            with action:
                submitted = st.form_submit_button(
                    "Run Agents", type="primary", disabled=service is None, use_container_width=True
                )
            with st.expander("Run settings"):
                st.text_input("Case ID", value="interactive-demo", key="case_id", max_chars=80)
                st.caption(
                    "Scope: respiratory illness & privacy. Output: citation-bound review points. Other clinical domains are not covered by this corpus."
                )
        if submitted:
            payload = {
                "case_id": st.session_state.case_id.strip(),
                "patient_summary": st.session_state.case_summary.strip(),
                "question": st.session_state.review_question.strip(),
                "top_k": st.session_state.top_k,
            }
            if (
                not payload["case_id"]
                or len(payload["patient_summary"]) < 10
                or len(payload["question"]) < 5
            ):
                st.session_state.pop("active_review", None)
                entry = None
                st.warning(
                    "Enter a case ID, at least 10 characters of synthetic case information, and a question of at least 5 characters."
                )
            else:
                run_review(payload)
                entry = st.session_state.get("active_review")
        if entry:
            st.caption(
                "Result snapshot below is from a completed run; edits above are not applied until you run again."
            )
        render_answer(entry)
    with context:
        result = entry["result"] if entry else None
        render_sources(result)
        render_workflow(result)
        render_metrics(result)

with evaluate:
    st.subheader("Evaluation Lab")
    st.markdown("### Offline Challenge Suite")
    st.caption(
        "20 synthetic development checks · Always offline, even when the backend uses a model. "
        "Known limitations count as unmet expectations, not passes."
    )
    if st.button("Run Offline Checks", type="primary", disabled=service is None):
        st.session_state.pop("offline_evaluation", None)
        try:
            st.session_state.offline_evaluation = post("/v1/evaluations/offline")
        except (httpx.HTTPError, ValueError) as exc:
            render_request_error(exc)
    if "offline_evaluation" in st.session_state:
        offline_report = st.session_state.offline_evaluation
        cols = st.columns(4)
        cols[0].metric("Checks passed", f"{offline_report['passed_cases']} / {offline_report['case_count']}")
        cols[1].metric("Known limitations", str(offline_report["known_limitations"]))
        cols[2].metric("Unexpected failures", str(offline_report["failed_cases"]))
        cols[3].metric("Model API calls", str(offline_report["model_api_calls"]))
        if offline_report["known_limitations"] or offline_report["failed_cases"]:
            st.warning("Not all expectations are met. Inspect the limitations and failures below.")
        st.dataframe([
            {key: row[key] for key in ("case_id", "kind", "expected", "observed", "outcome")}
            for row in offline_report["results"]
        ], hide_index=True, use_container_width=True)
        for row in offline_report["results"]:
            if row["outcome"] != "passed":
                with st.expander(row["case_id"] + " · " + row["outcome"]):
                    st.text(row["note"])
                    st.json(row["details"])
        st.caption(offline_report["metric_note"])
        st.download_button("Download offline report", json.dumps(offline_report, indent=2),
                           "offline-challenges.json", "application/json")
    st.divider()
    st.markdown("### Six-case Retrieval Smoke Set")
    st.write("Six synthetic smoke cases test retrieval, citation IDs, support checks, and latency.")
    st.info(
        "This is an engineering baseline, not a clinical benchmark. A 100% text-match score does not establish medical accuracy."
    )
    st.caption(
        "Uses the backend's active reasoner. Model mode makes billable API calls; extractive mode runs offline."
    )
    if service and service.get("pipeline_mode") == "adaptive":
        st.warning("Adaptive batch: up to 42 model calls for six cases. This may take several minutes.")
    if st.button("Run Evaluation", type="primary", disabled=service is None):
        st.session_state.pop("evaluation", None)
        try:
            with st.spinner("Running the evaluation set…"):
                st.session_state.evaluation = post("/v1/evaluations/run")
        except (httpx.HTTPError, ValueError) as exc:
            render_request_error(exc)
    if "evaluation" in st.session_state:
        report = st.session_state.evaluation
        cols = st.columns(4)
        cols[0].metric("Retrieval Recall@K", f"{report['mean_retrieval_recall']:.0%}")
        cols[1].metric("Expected citation precision", f"{report['mean_citation_precision']:.0%}")
        cols[2].metric("Candidate support check", f"{report['mean_supported_claim_rate']:.0%}")
        cols[3].metric("P95 pipeline latency", f"{report['p95_latency_ms']:.2f} ms")
        st.caption(
            f"{report['dataset_name']} · {report['case_count']} cases · {report['reasoner_mode']} · Cases with review flags: {report['conflict_case_rate']:.0%}"
        )
        if report.get("pipeline_mode") == "adaptive":
            st.caption(
                f"No-answer cases: {report['abstention_case_rate']:.0%} · "
                f"Model/budget errors: {report['error_case_rate']:.0%} · "
                "See initial support and repair attempts per case below."
            )
        st.dataframe(report["results"], hide_index=True, use_container_width=True)
        st.caption(report["metric_note"])
        st.download_button(
            "Download evaluation JSON",
            json.dumps(report, indent=2),
            "evaluation.json",
            "application/json",
        )

with cases:
    st.subheader("Recent Cases")
    st.caption(
        "The last five successful runs in this browser session. Export records to keep them; this is not a patient database."
    )
    if not recent:
        st.info("Run a synthetic case or the conflict demo to create your first record.")
    for index, item in enumerate(recent):
        result = item["result"]
        with st.container(border=True):
            st.text(f"{result['case_id']} · {item['time']}")
            st.caption(
                f"{result['status']} · {len(result['conflicts'])} review flags · {result['metrics']['reasoner_mode']}"
            )
            with st.expander("Result snapshot"):
                st.json(item)
            st.download_button(
                "Export record",
                json.dumps(item, indent=2),
                "review-history.json",
                "application/json",
                key=f"history-{index}",
            )

with playground:
    st.subheader("Conflict Detection Playground")
    st.write(
        "Test what happens when the reasoner emits an incorrect statement or an invented citation."
    )
    st.warning(
        "This fixed, offline fixture deliberately injects two errors. It is not an observed model failure rate."
    )
    st.markdown(
        "1. Extract a review point from one source.\n2. Add a known counterexample and a nonexistent citation.\n3. Run the verifier and conflict detector on all three statements."
    )
    if st.button("Run Conflict Demo", disabled=service is None, type="primary"):
        run_review()
    demo_entry = st.session_state.get("active_review")
    if demo_entry and demo_entry["result"].get("is_demo"):
        render_status(demo_entry["result"])
        st.info(
            "Open Ask → Conflict Analysis for the flagged statements and Ask → Agent Outputs for the recorded checks."
        )

with about:
    st.subheader("About MedAgent")
    st.write(
        "An inspectable healthcare evidence-review prototype, designed to demonstrate retrieval, structured outputs, verification, evaluation, and deployment engineering."
    )
    st.markdown(
        "**What runs today**\n\n- FastAPI + Streamlit, with six curated evidence chunks and six smoke cases.\n- An offline BM25 / extractive / rule-verifier baseline.\n- Optional adaptive mode: model-selected local searches, structured drafting, semantic checks with quote validation, and at most one repair.\n- Adaptive control flow is tested with scripted responses; live model quality has not been validated.\n- Pre-repair audit records, bounded calls, measured timings, and exportable run records."
    )
    st.markdown(
        "**What it does not establish**\n\n- Clinical accuracy, patient-specific treatment suitability, or an independently measured hallucination rate.\n- Independent medical validation: adaptive roles share the configured model and may share its errors.\n- General medical coverage, PDF ingestion, persistent case storage, or production deployment readiness."
    )
    st.markdown("**Project milestones**")
    st.table(
        [
            {
                "Milestone": "1 · Repository & architecture",
                "Status": "Local structure and architecture documented; GitHub publication pending",
            },
            {
                "Milestone": "2 · Agent + retrieval + evaluator",
                "Status": "Offline baseline runs; live model validation and independent eval set pending",
            },
            {
                "Milestone": "3 · UI, README, results & video",
            "Status": "English UI, README and evaluation table available; release artifacts tracked in docs",
            },
            {"Milestone": "4 · Resume", "Status": "Not completed in this project"},
            {"Milestone": "5 · Applications", "Status": "Not completed in this project"},
        ]
    )
    st.caption(
        "Docker API and UI passed local smoke checks on 2026-09-05. This is not a production deployment."
    )
