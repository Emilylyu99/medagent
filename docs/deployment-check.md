# Local Docker verification — 2026-09-05

Environment: Docker Desktop on macOS ARM64, Docker Engine 29.5.3, Compose 5.1.4.

The release was built and started as the isolated Compose project `medagent-step3`,
using ports 18000 / 18501 so existing development services on 8000 / 8501 were unaffected.

```bash
API_PORT=18000 UI_PORT=18501 REASONER_MODE=extractive OPENAI_API_KEY= OPENAI_MODEL= \
  docker compose -p medagent-step3 up --build -d --wait
```

| Check | Observed result |
| --- | --- |
| Container build | API and UI images built successfully |
| API health check | Healthy |
| Streamlit health check | Healthy |
| Container user | Both run as `appuser`, not root |
| Published interfaces | Both bind to 127.0.0.1 |
| Browser to container API workflow | Normal review, evidence expansion, trace display, conflict demo, evaluation and history completed |
| Browser JavaScript errors | None reported during the smoke flow |
| Real model requests | None; extractive mode, model credentials blank |

The browser smoke pass used `scripts/record_demo.cjs --quick` with `DEMO_URL` set to
`http://localhost:18501` and `DEMO_API_URL` set to `http://localhost:18000`.
This validates a local container workflow, not production security, scaling, authentication,
observability, clinical safety, or cloud hosting.

Builds currently use bounded dependency ranges and a Python 3.12 base tag. Future releases
should pin a reviewed lockfile and base-image digest before claiming bit-for-bit reproducibility.
