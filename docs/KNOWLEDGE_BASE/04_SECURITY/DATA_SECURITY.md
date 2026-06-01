# Zensers Data Security and Privacy Protection Design

> **Document Version**: v1.0  
> **Creation Date**: 2026-04-04  
> **Update Date**: 2026-04-05  
> **Status**: Design Phase  
> **Related Documents**: ARCHITECTURE.md v1.2, COST_OPTIMIZATION.md v1.1, GLOSSARY.md

---

## 1. Security Architecture Overview

### 1.1 Security Layered Model

```
┌─────────────────────────────────────────────────────────────────┐
│                      Application Security Layer                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ Identity    │  │ Access      │  │ Audit Log               │ │
│  │ (OAuth2/JWT)│  │ Control     │  │ (Tamper-proof)          │ │
│  │             │  │ (RBAC)      │  │                         │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│                       Data Security Layer                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ Transport   │  │ Storage     │  │ Data Anonymization     │ │
│  │ Encryption  │  │ Encryption  │  │ (Dynamic/Static)        │ │
│  │ (TLS 1.3)   │  │ (AES-256)   │  │                         │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│                      Infrastructure Layer                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ Key         │  │ Secure      │  │ Network Isolation       │ │
│  │ Management  │  │ Storage     │  │ (VPC/Firewall)          │ │
│  │ (KMS/HSM)   │  │ (Encrypted) │  │                         │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Data Classification System

| Data Level | Definition | Example | Protection Requirements |
|------------|-----------|---------|----------------------|
| **L1-Public** | Publicly accessible data | Industry report summaries, public statistics | Standard protection |
| **L2-Internal** | System internal use | Research templates, config info | Access control |
| **L3-Sensitive** | User business data | Full research reports, analysis results | Encrypted storage |
| **L4-Confidential** | Personal privacy data | Survey responses, contact info | Full encryption + anonymization |
| **L5-Critical** | System core keys | API keys, encryption master keys | HSM isolation |
