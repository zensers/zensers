# Zensers Cloud Deployment Configuration Templates

> **Status**: Design Phase | **Version**: v1.0 | Supports Docker / K8s / Serverless

## 1. Directory Structure

```
deployment/
├── docker/                    # Docker deployment config
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── docker-compose.prod.yml
├── kubernetes/                # K8s deployment config
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   ├── deployment-api.yaml
│   ├── deployment-worker.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   └── hpa.yaml              # Auto scaling
├── serverless/               # Serverless deployment config
│   ├── serverless.yml        # Serverless Framework
│   └── vercel.json           # Vercel deployment
└── terraform/                # Infrastructure as Code (reserved)
    └── main.tf
```
