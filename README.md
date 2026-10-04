# FlowOps

[![CI](https://github.com/Jemade/flowOPS/actions/workflows/ci.yml/badge.svg)](https://github.com/Jemade/flowOPS/actions/workflows/ci.yml)

A Python data pipeline workbench with a FastAPI dashboard and LangGraph workflow. Submit a dataset, follow its processing stages, and inspect validation and evaluation results.

## Features

- Ingestion, transformation, validation, and evaluation stages.
- Pipeline submission, status tracking, history, and deletion.
- Local data storage with optional S3 and DynamoDB integrations.
- Health, readiness, and metrics endpoints.
- Docker Compose with LocalStack and Kubernetes manifests.

## Run locally

Requires Python 3.11 or newer.

```bash
git clone https://github.com/Jemade/flowOPS.git
cd flowOPS
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000 for the dashboard and http://localhost:8000/docs for the API. Configuration uses the `FLOWOPS_` prefix; see `app/config.py` and `.env.example`.

## Containers and checks

```bash
docker compose up --build
pytest -q
```

Compose includes LocalStack on port 4566. Configure AWS credentials and resources for the S3/DynamoDB path. Kubernetes resources are in `k8s/`.

## Code map

- `app/`: API, workflow graph, state store, and storage integrations.
- `data/`: demonstration inputs.
- `tests/`: automated checks.
- `k8s/`: deployment resources.

## Current scope

Pipeline execution runs in the API process through asynchronous tasks. It is not a durable distributed job queue. In-memory state and metrics do not survive a restart; configured external storage has separate persistence.

## Engineering and contribution guide

Read the [engineering notes](docs/ENGINEERING.md) for implementation boundaries and verification commands, the [review checklist](docs/REVIEW_CHECKLIST.md) for evidence still required, and [CONTRIBUTING.md](CONTRIBUTING.md) to propose changes. Report vulnerabilities through [SECURITY.md](SECURITY.md).

[![Repository hygiene](https://github.com/Jemade/flowOPS/actions/workflows/repository-hygiene.yml/badge.svg)](https://github.com/Jemade/flowOPS/actions/workflows/repository-hygiene.yml)
