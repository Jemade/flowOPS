# Deployment Details and Infrastructure Record

This document records the production deployment configuration, public endpoints, and operational metadata for FlowOps.

## Public Service Endpoints

- Live Application: https://flowops-k1yz.onrender.com
- Dashboard UI: https://flowops-k1yz.onrender.com/
- Interactive OpenAPI Docs (Swagger): https://flowops-k1yz.onrender.com/docs
- Alternative API Docs (ReDoc): https://flowops-k1yz.onrender.com/redoc
- Health Probe (Liveness): https://flowops-k1yz.onrender.com/health
- Readiness Probe: https://flowops-k1yz.onrender.com/ready
- Metrics Endpoint: https://flowops-k1yz.onrender.com/metrics

## Platform Configuration

- Hosting Provider: Render (Free Web Service)
- Service Name: flowOPS
- Service ID: srv-dah8q0dbedkc739kgbgg
- Service Region: Oregon, USA (us-west)
- Runtime: Docker
- Base Image: python:3.11-slim
- Internal Port: 8000 (dynamically mapped by Render via PORT environment variable)
- Deployment Strategy: Automated rolling deployment triggered on git push to the main branch

## Repository and CI/CD

- Source Code: https://github.com/Jemade/flowOPS
- Default Branch: main
- Automation: GitHub Actions (.github/workflows/ci.yml)
- Verification: Unit tests (pytest), packaging verification, and container smoke testing on push

## Security Note

Sensitive credentials (such as API keys, personal access tokens, and cloud secrets) must never be committed to source control. Configure all sensitive tokens in the Render service settings under Environment Variables or using a dedicated secrets manager.
