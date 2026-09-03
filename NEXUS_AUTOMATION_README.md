# NEXUS Automated Engineering System — v1

## Purpose
Turn NEXUS development into a repeatable quality-gated workflow:

`Change → Test → Diagnose → Fix → Retest → Deploy`

## Files
- `tests/test_nexus_regression.py` — regression tests for Phase 3 research/evidence behavior.
- `pytest.ini` — tells pytest where to find tests.
- `requirements-test.txt` — test-only dependency.
- `run_nexus_tests.py` — one-command local runner.
- `.github/workflows/nexus-tests.yml` — GitHub automatic quality gate on push, pull request, or manual run.

## Install
```bash
python -m pip install -r requirements-test.txt
```

## Run locally
```bash
python run_nexus_tests.py
```

or:
```bash
pytest
```

## GitHub layout
Put these files beside your existing production `streamlit_app.py`:

```text
NEXUS/
├── streamlit_app.py
├── pytest.ini
├── requirements-test.txt
├── run_nexus_tests.py
├── tests/
│   └── test_nexus_regression.py
└── .github/
    └── workflows/
        └── nexus-tests.yml
```

## Safety rule
The automation does not modify production code, weaken tests, or deploy changes. A failing gate stops the workflow.

## Next automation layers
1. Add Phase 2 routing/provider regression tests.
2. Add attachment/data regression tests.
3. Add live research smoke tests on a scheduled workflow with secrets.
4. Add security/dependency scanning.
5. Add deployment only after all gates pass.
