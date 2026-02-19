# Contributing to AEGIS

First off, thank you for considering contributing to AEGIS! It's people like you that make AEGIS such a great tool for the agentic future.

## 🤝 Code of Conduct

By participating in this project, you agree to abide by our Code of Conduct. We expect all contributors to treat one another with respect and kindness.

## 🚀 Getting Started

1.  **Fork the repository** on GitHub.
2.  **Clone your fork** locally:
    ```bash
    git clone https://github.com/YOUR_USERNAME/AEGIS.git
    cd AEGIS
    ```
3.  **Create a branch** for your feature or bugfix:
    ```bash
    git checkout -b feature/amazing-feature
    ```

## 🛠️ Development Setup

### Backend (Python)
We use Python 3.11+ and `pytest` for testing.

```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/Mac: source venv/bin/activate
pip install -r requirements.txt

# Run tests
python -m pytest
```

### Frontend (Next.js)
We use Node.js 18+ and `npm`.

```bash
cd frontend
npm install
npm run dev
```

### Full Stack (Docker)
The easiest way to run the full stack is via Docker Compose:

```bash
docker compose up -d
```

## 🧪 Testing

*   Ensure all new features include unit tests.
*   Run the full test suite before submitting your PR.
*   If you change the policy engine, add test cases to `policies/tests` (if applicable) or verify with `opa test`.

## 📝 Pull Request Process

1.  Ensure your code adheres to the project's style (**Black** for Python, **Prettier** for JS/TS).
2.  Update the `README.md` with details of changes to the interface, if applicable.
3.  Submit your Pull Request against the `main` branch.
4.  Describe your changes in detail in the PR description. Link to any relevant issues.

## 🐞 Reporting Bugs

Please use the GitHub Issues tab to report bugs. Include:
*   Your operating system and browser version.
*   Steps to reproduce the bug.
*   Expected vs. actual behavior.
*   Screenshots or logs if possible.

## 💡 Feature Requests

We love new ideas! Please open an issue to discuss your idea before implementing it, to ensure it aligns with the project roadmap.

---

Thank you for your contribution!
