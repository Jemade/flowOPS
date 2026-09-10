# FlowOps

FlowOps is a lightweight data pipeline orchestration engine and dashboard built with Python, FastAPI, and LangGraph. It provides a simple way to submit, execute, track, and evaluate data processing workflows with support for local file storage, Amazon S3, and DynamoDB.

This document covers the system architecture, component breakdown, local setup instructions, containerization with Docker, and production deployment on Kubernetes.

---

## Table of Contents

1. Architecture Overview
2. System Components
3. Pipeline Execution Lifecycle
4. Local Development Setup
5. Running with Docker
6. Running with Docker Compose and LocalStack
7. Kubernetes Deployment Guide
8. API Reference
9. Configuration Reference
10. Testing

---

## 1. Architecture Overview

FlowOps is structured as a modular asynchronous service. It separates ingestion, state management, graph-based workflow execution, and presentation into clean layers.

```
       +-------------------------------------------------------+
       |                  Client / Web Browser                 |
       +-------------------------------------------------------+
                                   |
                                   v  (HTTP / JSON)
       +-------------------------------------------------------+
       |                   FastAPI API Layer                   |
       |  - Dashboard (Static Files at /)                      |
       |  - Pipeline Trigger (POST /pipelines/run)             |
       |  - Status and Tracking (GET /pipelines/{id})          |
       |  - Health and Metrics (/health, /ready, /metrics)     |
       +-------------------------------------------------------+
                                   |
         +-------------------------+-------------------------+
         |                                                   |
         v                                                   v
+-----------------------+                         +-----------------------+
|  Pipeline Store       |                         |  Workflow Engine      |
|  - In-Memory State    |                         |  - LangGraph DAG      |
|  - DynamoDB Fallback  |                         |  - 4 Discrete Stages  |
+-----------------------+                         +-----------------------+
         |                                                   |
         |                                                   v
         |                                        +-----------------------+
         |                                        |  Object Storage       |
         +--------------------------------------->|  - Local Files / Demo |
                                                  |  - AWS S3 Buckets     |
                                                  +-----------------------+
```

### Key Architectural Principles

- Asynchronous by design: Incoming pipeline requests return immediately with an HTTP 202 Accepted status and a unique tracking ID. The pipeline execution runs asynchronously in the background.
- State-driven workflow: Workflows are modeled as a directed acyclic graph (DAG) using LangGraph. Each stage updates the shared pipeline state and publishes progress back to the store.
- Cloud-ready with zero-dependency fallback: The system automatically uses DynamoDB and S3 if configured. If no AWS credentials or endpoint URL are provided, it automatically falls back to an in-memory store and local file storage with zero configuration needed.

---

## 2. System Components

### 2.1 API and Presentation Layer (`app/main.py`)
- Framework: FastAPI running on Uvicorn ASGI server.
- Web UI: Serves a lightweight single-page dashboard directly from the `static/` directory.
- Background Tasks: Uses Python asyncio tasks to execute workflows without blocking API request threads.
- Observability: Exposes dedicated `/health` (liveness), `/ready` (readiness), and `/metrics` endpoints.

### 2.2 Workflow Execution Engine (`app/workflow.py`)
The pipeline runs through a LangGraph `StateGraph` compiled workflow consisting of four sequential stages:

1. Ingestion (`ingest`):
   - Accepts raw CSV input passed inline in the request body, loaded from a local file path, or fetched from an S3 bucket (`s3://bucket/key`).
   - Parses CSV content into structured Python dictionaries.

2. Transformation (`transform`):
   - Performs automatic type inference and coercion across dataset columns.
   - Automatically converts string values containing numbers into native integer and floating-point types while preserving non-numeric strings.

3. Validation (`validate`):
   - Verifies row count and checks for data integrity.
   - Flags empty datasets and collects schema validation warnings.

4. Evaluation (`evaluate`):
   - Computes a dataset quality score (1.0 for valid datasets, 0.0 for empty or malformed datasets).
   - Assigns a qualitative rating ("good" or "poor").

### 2.3 State Management Layer (`app/store.py`)
- Implements `PipelineStore`, which tracks all active, completed, and failed pipeline runs.
- Includes a thread-safe in-memory cache protected by an `asyncio.Lock`.
- When an AWS endpoint URL is configured, every state update is mirrored into an Amazon DynamoDB table (`flowops-pipelines`).

### 2.4 Storage Abstraction Layer (`app/storage.py`)
- Implements `ObjectStorage`, offering a unified API for reading datasets.
- Supports three data sources:
  - `demo` or `fixture`: Loads the bundled sample dataset from `data/demo.csv`.
  - `s3://...`: Downloads objects using Boto3 from an S3 bucket or LocalStack.
  - Local path: Reads directly from the local filesystem.

---

## 3. Pipeline Execution Lifecycle

When a client initiates a pipeline, the following lifecycle occurs:

1. Submission:
   - Client sends `POST /pipelines/run` with a source type (`demo`, `inline`, or local path) and optional CSV text.
   - API creates a record with status `queued` and progress 0%.
   - API returns HTTP 202 with tracking ID and status URL.

2. Execution:
   - Status transitions to `running`.
   - Stage 1: Ingestion runs, sets progress to 20%.
   - Stage 2: Transformation runs, sets progress to 45%.
   - Stage 3: Validation runs, sets progress to 70%.
   - Stage 4: Evaluation runs, sets progress to 90%.

3. Completion:
   - Final status transitions to `succeeded` (or `failed` if an exception occurred).
   - Progress reaches 100%.
   - Transformed rows and evaluation metrics are attached to the pipeline record.

---

## 4. Local Development Setup

### Prerequisites
- Python 3.11 or higher
- Git

### Installation Steps

1. Clone the repository:
```bash
git clone https://github.com/Jemade/flowOPS.git
cd flowOPS
```

2. Create and activate a Python virtual environment:
- On Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
```
- On Windows (PowerShell):
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

3. Install dependencies:
```bash
pip install -e ".[dev]"
```
Tip: If you have `uv` installed, you can run `uv pip install -e ".[dev]"` for faster installation.

4. Run the application:
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

5. Open your browser:
- Dashboard: http://127.0.0.1:8000/
- API Documentation: http://127.0.0.1:8000/docs
- Health Check: http://127.0.0.1:8000/health

---

## 5. Running with Docker

FlowOps includes a production-ready Dockerfile based on `python:3.11-slim`. The container runs as an unprivileged non-root user for security.

### Build the Docker Image

```bash
docker build -t flowops:latest .
```

### Run the Container in Standalone Mode

In standalone mode, FlowOps uses the in-memory store and local data fixtures:

```bash
docker run -d \
  --name flowops-app \
  -p 8000:8000 \
  flowops:latest
```

Access the dashboard at http://localhost:8000.

To view container logs:
```bash
docker logs -f flowops-app
```

To stop and remove the container:
```bash
docker stop flowops-app && docker rm flowops-app
```

---

## 6. Running with Docker Compose and LocalStack

To run FlowOps with full cloud emulation (Amazon S3 and DynamoDB), use the included `docker-compose.yml`. This starts both LocalStack and FlowOps, and automatically provisions the S3 bucket and DynamoDB table on startup.

### Start the Services

```bash
docker compose up -d --build
```

### What Docker Compose Does

1. Launches LocalStack on port 4566.
2. Runs `scripts/seed-localstack.sh` on LocalStack startup to create:
   - S3 Bucket: `s3://flowops-data`
   - DynamoDB Table: `flowops-pipelines`
3. Builds the FlowOps API image and connects it to LocalStack.
4. Exposes FlowOps at http://localhost:8000.

### Stop the Services

```bash
docker compose down
```

---

## 7. Kubernetes Deployment Guide

The repository includes complete Kubernetes manifests located in the `k8s/` directory.

### Manifest Structure

- `k8s/namespace.yaml`: Creates the dedicated `flowops` namespace.
- `k8s/configmap.yaml`: Configures environment variables (AWS region, bucket, table).
- `k8s/deployment.yaml`: Defines a 2-replica Deployment with rolling update strategy, non-root security context, resource requests/limits, and liveness/readiness probes.
- `k8s/service.yaml`: Creates a ClusterIP Service routing port 80 to container port 8000.
- `k8s/ingress.yaml`: Configures an Ingress resource for external HTTP access.
- `k8s/hpa.yaml`: HorizontalPodAutoscaler scaling from 2 to 10 pods based on CPU and memory utilization.
- `k8s/kustomization.yaml`: Bundles all resources for one-command deployment.

### Deploying to a Kubernetes Cluster

1. Ensure your cluster is running (Minikube, Kind, EKS, GKE, or AKS) and `kubectl` is configured:
```bash
kubectl cluster-info
```

2. If using Minikube or Kind, load your local Docker image into the cluster:
- For Minikube:
```bash
minikube image load flowops:latest
```
- For Kind:
```bash
kind load docker-image flowops:latest
```

3. Apply all manifests using Kustomize:
```bash
kubectl apply -k k8s/
```

4. Verify that the pods and services are running:
```bash
kubectl get pods -n flowops
kubectl get svc -n flowops
```

5. Test the application via port-forwarding:
```bash
kubectl port-forward svc/flowops-service -n flowops 8080:80
```
Open http://localhost:8080 in your browser to access the dashboard.

### Inspecting Probes and Logs

Check the pod logs:
```bash
kubectl logs -n flowops -l app.kubernetes.io/name=flowops -f
```

Check deployment rollout status:
```bash
kubectl rollout status deployment/flowops-api -n flowops
```

### Cleaning Up Kubernetes Resources

To delete all deployed resources:
```bash
kubectl delete -k k8s/
```

---

## 8. API Reference

### Health and Monitoring

- `GET /health`: Basic health check. Returns `{"status": "ok"}`.
- `GET /ready`: Readiness probe for Kubernetes. Returns `{"status": "ready"}`.
- `GET /metrics`: Returns operational counts:
  ```json
  {
    "pipelines_started": 12,
    "pipelines_succeeded": 11,
    "pipelines_failed": 1
  }
  ```

### Pipelines

#### 1. Trigger Pipeline Run
- Endpoint: `POST /pipelines/run`
- Status Code: `202 Accepted`
- Request Body (Demo Run):
  ```json
  {
    "name": "sales-batch-run",
    "source": "demo"
  }
  ```
- Request Body (Inline CSV Data):
  ```json
  {
    "name": "custom-inline-data",
    "source": "inline",
    "text": "transaction_id,amount,customer\n101,45.50,Alice\n102,99.00,Bob\n"
  }
  ```
- Response:
  ```json
  {
    "tracking_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "pipeline_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "status": "queued",
    "status_url": "http://127.0.0.1:8000/pipelines/a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d"
  }
  ```

#### 2. Get Pipeline Details
- Endpoint: `GET /pipelines/{pipeline_id}`
- Response:
  ```json
  {
    "id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "tracking_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "name": "sales-batch-run",
    "status": "succeeded",
    "current_stage": "completed",
    "progress": 100,
    "stage_history": [
      "queued",
      "ingestion",
      "transformation",
      "validation",
      "evaluation",
      "completed"
    ],
    "result": {
      "validation": {
        "valid": true,
        "row_count": 3,
        "errors": []
      },
      "evaluation": {
        "score": 1.0,
        "quality": "good"
      },
      "rows": [
        {"id": 1, "value": 10},
        {"id": 2, "value": 20},
        {"id": 3, "value": 30}
      ]
    },
    "error": null
  }
  ```

#### 3. List All Pipelines
- Endpoint: `GET /pipelines`
- Returns a list of pipeline summary objects.

#### 4. Delete Pipeline Record
- Endpoint: `DELETE /pipelines/{pipeline_id}`
- Status Code: `204 No Content`

---

## 9. Configuration Reference

All settings can be configured through environment variables or a local `.env` file. Variable names are prefixed with `FLOWOPS_`.

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `FLOWOPS_APP_NAME` | `FlowOps` | Application display name |
| `FLOWOPS_AWS_REGION` | `us-east-1` | AWS region for DynamoDB and S3 |
| `FLOWOPS_AWS_ENDPOINT_URL` | `None` | Custom endpoint for LocalStack or AWS emulator |
| `FLOWOPS_S3_BUCKET` | `flowops-data` | Target S3 bucket for data storage |
| `FLOWOPS_DYNAMODB_TABLE` | `flowops-pipelines` | DynamoDB table name for pipeline metadata |
| `FLOWOPS_DEMO_FIXTURE` | `demo.csv` | Default CSV file inside the `data/` folder |

---

## 10. Testing

The project uses pytest with asyncio support. Run the full test suite with:

```bash
pytest
```

To run with verbose output:
```bash
pytest -v
```

All tests run without requiring external AWS services or LocalStack by utilizing the built-in in-memory fallback.
