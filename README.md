# 🛡️ AEGIS — Agentic Identity & Access Management

<div align="center">
  <h3><strong>The Deterministic Execution Proxy for Autonomous AI Agents</strong></h3>
  <br>

  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
  [![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
  [![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=flat&logo=docker&logoColor=white)](https://www.docker.com/)
  [![Kubernetes](https://img.shields.io/badge/kubernetes-%23326ce5.svg?style=flat&logo=kubernetes&logoColor=white)](https://kubernetes.io/)
  [![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

  <br>

  > **"No agent owns a key; the system lends the capability to act in real-time under surveillance."**
</div>

---

## 🛑 The Problem
As AI agents evolve from simple chatbots to autonomous actors that can execute code, manipulate databases, and spend money, the security risks explode.
*   **Key Leaks**: Giving an agent an API key is a security nightmare.
*   **Runaway Costs**: Infinite loops or malicious prompts can drain budgets in minutes.
*   **Compliance**: Who executes the action? The user or the bot? Where is the audit trail?

## ✅ The Solution: AEGIS
**AEGIS** is a secure middleware—a **Deterministic Execution Proxy**—that sits between your AI agents and the external world. It ensures that no agent ever holds a raw credential. Instead, agents request actions through AEGIS, which evaluates policies, checks budgets, and logs every single byte before executing the call on the agent's behalf.

## ⚡ Key Capabilities

| Feature | Description |
| :--- | :--- |
| 🛡️ **Zero-Trust Proxy** | Agents never see API keys. Credentials are injected Just-In-Time by AEGIS. |
| 💰 **Economic Guardrails** | Strict per-agent wallets with daily/monthly spending caps. |
| 📜 **Policy as Code** | Granular control via **Open Policy Agent (Rego)**. Restrict models, endpoints, and payloads. |
| 🕵️ **Forensic Audit** | Immutable, hash-chained logs of every request/response for compliance and debugging. |
| 👨‍✈️ **Human-in-the-Loop** | High-risk actions (e.g., `transfer_funds`) trigger a manual approval workflow. |
| 🔌 **Circuit Breaker** | Auto-suspends agents exhibiting anomalous behavior or high error rates. |
| 📊 **Observability** | Real-time monitoring with **Prometheus**, **Grafana**, and WebSocket event streams. |

## 🏗️ Architecture

AEGIS employs a microservices-inspired architecture designed for high availability and security.

![AEGIS Architecture](https://mermaid.ink/img/pako:eNp1ks1qwzAQhV9F3DpZIIUWXRRKtykUuummqyyOqJFtk2hLToTSd68cJ0kbCrFh5s98Mxo9C5YSjIX1S-Eq5oWz_iPLhX_KhXBKuLcP4XjA8XjA8XzBWYbjAcfTBWcZjifhOBPuIxwPwn2E48FwzZz1wrlX90Kol1y4D_dCqJdcuF-r-7kQzlm3LoTTuhDOrQvhtC7mn8f9O7cuLHzBfQnvS3hfwvsS3pfwvoT3rz68r_3hfe0P72t_eF_7w_vaH97X_vC-9of3tT-8r_3hfe0P72t_eF_7w_vaH97X_vC-9of3tT-8r_3hfe0P72t_eF_7w_vaH97X_vC_9of3tT-8r_3hfe0P72t_eF_7w_vaH97X_vC-9of3tT-8r_3hfW4v8B8)

## 🚀 Quick Start

### Prerequisites
*   [Docker Desktop](https://www.docker.com/products/docker-desktop)
*   [Git](https://git-scm.com/)

### 1-Minute Deployment (Docker Compose)
This spins up the entire stack: Backend, Frontend, Postgres, Redis, OPA, Prometheus, and Grafana.

```bash
# 1. Clone the repo
git clone https://github.com/lihu-garcia/AEGIS.git
cd AEGIS

# 2. Setup secrets
cp .env.example .env
# (Optional) Edit .env to set your own secrets

# 3. Launch
docker compose up -d
```

Navigate to **http://localhost:3000** to access the AEGIS Dashboard.

### Production Deployment (Kubernetes)
For production environments, use our official Helm chart located in `helm/`.

```bash
helm install aegis ./helm/aegis -n aegis-system --create-namespace
```
See the [High Availability Guide](docs/ha-infrastructure.md) for detailed production configurations.

## 🛠️ Python SDK
Integrate your agents seamlessly using the AEGIS SDK.

```python
from aegis_sdk import AegisClient

client = AegisClient(
    base_url="http://localhost:8000",
    api_key="YOUR_AGENT_API_KEY",
    agent_id="YOUR_AGENT_ID"
)

# The agent executes an action without ever knowing the OpenAI key
response = client.execute(
    service_name="openai",
    action="chat.completion",
    target_url="https://api.openai.com/v1/chat/completions",
    method="POST",
    body={
        "model": "gpt-4",
        "messages": [{"role": "user", "content": "Hello!"}]
    },
    estimated_cost_usd=0.01
)
```

## 📂 Project Structure

```text
AEGIS/
├── backend/                # FastAPI application (Python)
├── frontend/               # Dashboard (Next.js, TypeScript)
├── sdk/                    # Client libraries
├── policies/               # OPA Rego policy definitions
├── helm/                   # Kubernetes deployment charts
├── monitoring/             # Prometheus & Grafana configs
├── nginx/                  # Edge proxy configuration
└── docs/                   # Additional documentation
```

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to set up your development environment and submit pull requests.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
