# Zensers - Installation Guide

## Prerequisites

- **Python 3.10+** — [Download](https://www.python.org/downloads/)
- **Node.js 18+** — [Download](https://nodejs.org/)
- **Git** — [Download](https://git-scm.com/downloads)

Verify installations:

```bash
python --version
node --version
git --version
```

## 1. Clone the Repository

```bash
git clone https://github.com/sunchaokun/zensers.git
cd zensers
```

## 2. Backend Setup

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

## 3. Frontend Setup

```bash
cd web
npm install
cd ..
```

## 4. Configuration

```bash
# Environment variables
cp .env.example .env

# Application settings
cp config/settings.example.yaml config/settings.yaml
```

Edit `.env` and `config/settings.yaml` to fill in your API keys and other required values.

## 5. Running the Application

### Backend

```bash
uvicorn src.api.main:app --port 8000
```

The API will be available at `http://localhost:8000`.

### Frontend

```bash
cd web
npm run dev
```

The frontend will be available at `http://localhost:3000` (or the port shown in terminal).

## 6. Docker Setup

```bash
docker compose up -d
```

This starts both backend and frontend services. Access the application at the configured ports.

To stop:

```bash
docker compose down
```

## 7. Troubleshooting

| Issue | Solution |
|-------|----------|
| `pip install` fails | Ensure venv is activated. Upgrade pip: `pip install --upgrade pip` |
| `npm install` fails | Delete `node_modules` and `package-lock.json`, then retry |
| Port 8000 already in use | Use a different port: `uvicorn src.api.main:app --port 8001` |
| Missing API key errors | Verify `.env` and `config/settings.yaml` contain valid keys |
| Docker containers won't start | Run `docker compose logs` to check error messages |
| Python version mismatch | Use `pyenv` (macOS/Linux) or install the correct version directly |
| `uvicorn` command not found | Ensure venv is activated and `requirements.txt` installed successfully |
