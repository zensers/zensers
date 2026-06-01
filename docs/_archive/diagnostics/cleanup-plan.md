# Zensers Project Temporary File Cleanup Plan

Total usage: ~2.77 GB (60,035 files), of which safely cleanable ~1.89 GB

---

## Step 0: Protected List (Never Delete)

| Path | Description |
|------|-------------|
| `docs/` | Project documentation |
| `config/` | Configuration files |
| `src/` | Source code |
| `web/src/` | Frontend source code |
| `scripts/` | Build/analysis scripts |
| `prompts/` | LLM prompts |
| `.gitignore`, `README.md`, `LICENSE`, etc. | Project root files |
| `_archive/` | Legacy source code archive (not generated files) |
| `.sisyphus/` | Project planning documents |
| `venv/` | Python virtual environment (dependencies, do not clean) |
| `web/node_modules/` | Node dependencies (do not clean) |
| `web/package-lock.json` | Dependency lock file (needs committing) |

---

## Step 1: Completely Safe (Can Be Deleted Directly, No Side Effects)

| Target | Count | Size | Command | Regeneration Method |
|--------|-------|------|---------|---------------------|
| All `__pycache__` under `src/` | ~210 files | ~3.3 MB | `Get-ChildItem -Recurse src/__pycache__ \| Remove-Item -Recurse` | `pytest` auto-rebuilds |
| All `__pycache__` under `tests/` | ~170 files | ~5.6 MB | Same as above | `pytest` auto-rebuilds |
| `__pycache__` under `scripts/` | 1 file | 15 KB | Same as above | -- |
| `.pytest_cache/` | 5 files | 257 KB | `Remove-Item -Recurse .pytest_cache` | `pytest` auto-rebuilds |
| `web/tsconfig.tsbuildinfo` | 1 file | ~100 KB | `Remove-Item web/tsconfig.tsbuildinfo` | `npm run build` rebuilds |

**Subtotal: ~9.3 MB**

---

## Step 2: Safe (Can Be Deleted, Rebuilt on Demand as Needed)

| Target | Count | Size | Description |
|--------|-------|------|-------------|
| `logs/` | 8 files | ~4.3 MB | Can delete all or archive by date. `app.log.*` is rotated logs, old ones can be deleted |

**Subtotal: ~4.3 MB**

---

## Step 3: Safe But Rebuilding Takes Time (Can Be Deleted, Requires `npm run build`)

| Target | Count | Size | Command |
|--------|-------|------|---------|
| `web/.next/` | 157 files | **~190 MB** | `Remove-Item -Recurse web\.next` |

Rebuild: `cd web && npm run build` (takes 1-3 minutes)

**Subtotal: ~190 MB**

---

## Step 4: Needs Confirmation (System Artifacts, But May Still Be In Use)

| Target | Count | Size | Risk | Suggestion |
|--------|-------|------|------|------------|
| `output/reports/` | 125 files | ~8.5 MB | Medium — Already generated report files, will be lost if user has not exported important reports | Delete after confirming no important reports |
| `output/charts/` | 93 files | ~5.1 MB | Low — Chart cache, rebuilt on reanalysis | Can delete |
| `data/previews/` | 63 files | ~510 KB | Low — HTML preview cache | Can delete |
| `data/results/` | 112 files | ~96 MB | Medium — Research result storage, completed report history may be lost after system restart | Confirm no important history before deleting |
| `data/registries/` | 225 files | **~1.56 GB** | Medium — Vector index/cache, system will re-index after deletion | Largest usage, but deletion may affect memory retrieval speed |
| `data/sessions/` | 5,401 files | ~828 KB | Low — Small session archive JSON | Can delete (each ~150B) |

**Subtotal: ~1.67 GB** (mainly `data/registries`)

---

## Step 5: Do Not Clear For Now

| Target | Size | Reason |
|--------|------|--------|
| `_cleanup_backup_20260503_095703/` | ~729 KB | Contains old scripts, delete after confirming no longer needed |
| `data/knowledge/`, `data/backups/`, `data/users/` | Small | Contains user data and knowledge base state |
| `venv/` + `node_modules/` | ~666 MB | Environment dependencies, high recovery cost to delete |

---

## Suggested Cleanup Order

```
Step A: __pycache__ + .pytest_cache + tsbuildinfo   -> 9.3 MB, zero risk
Step B: logs/                                        -> 4.3 MB, zero risk
Step C: web/.next/                                   -> 190 MB, needs rebuild
Step D: data/previews/ + output/charts/              -> 5.6 MB, low risk
Step E: data/registries/ + data/results/             -> 1.66 GB, needs confirmation
```

First three steps (A+B+C) can be executed without worry, cleaning ~203 MB.  
Last two steps (D+E) require manual confirmation before execution, can reclaim ~1.67 GB.

---

## Appendix: Pre-Release Cleanup Checklist

If planning to release the project (open source, deploy to production environment), the following items require additional attention:

### 1. Red Sensitive Information — Must Handle

| Item | Status | Action |
|------|:------:|--------|
| `.env` contains real API Key `sk-f9f5...` | Exists | Rotate the key, add `.env` to `.gitignore` (**already there**), delete or replace with placeholder |
| `.env` contains plaintext database password `123456` | Weak password | Replace with placeholder |
| API Key placeholder in `config/settings.yaml` comments | Note | Already commented, no risk |
| Whether `.env` exists in Git history | Needs check | `git log --all --diff-filter=A -- .env` |

### 2. Yellow Development Data — Should Be Cleaned for Production

All files under `data/` were generated during development/testing. Production deployment should start from clean:

| Directory | Content | Suggestion |
|-----------|---------|------------|
| `data/*.db` (10 files) | SQLite databases — test users, temporary knowledge base | Delete, production initializes from Schema |
| `data/sessions/` (5,401 files) | Session history during development | Delete |
| `data/users/` | Development test user memory profiles | Delete |
| `data/tasks/` (77 files) | Research task definitions | Delete |
| `data/results/` (112 files) | Completed research results | Delete |
| `data/registries/` (225 files, 1.56 GB) | Vector index/cache | Delete |
| `data/previews/` (63 files) | HTML preview cache | Delete |
| `data/revisions/` | Document revision history | Delete |
| `data/survey_tasks/` | Survey tasks | Delete |
| `data/sentiment/` | Sentiment analysis cache | Delete |
| `data/knowledge/` | Knowledge base configuration | Keep templates, delete generated indexes |

### 3. Yellow System Artifacts — Should Be Cleaned for Production

| Directory | Suggestion |
|-----------|------------|
| `output/reports/` (125 files, 8.5 MB) | Delete, system generates on demand |
| `output/charts/` (93 files, 5.1 MB) | Delete, system generates on demand |
| `logs/` (8 files, 4.3 MB) | Delete, production logs start fresh |

### 4. Green Build Cache — Rebuild Before Production Deployment

| Directory | Action |
|-----------|--------|
| `web/.next/` (190 MB) | Delete then execute `npm run build` |
| `__pycache__/` (all) | Delete, auto-rebuilds at runtime |
| `.pytest_cache/` | Delete, development only |

### 5. Initialization Script Suggestion

Create a `scripts/reset-for-production.py` that executes the above cleanup in one click:

```python
# Pseudo-code
reset_items = [
    "data/*.db", "data/sessions/", "data/users/", "data/tasks/",
    "data/results/", "data/registries/", "data/previews/",
    "data/revisions/", "data/survey_tasks/", "data/sentiment/",
    "output/", "logs/", "web/.next/",
]
for path in reset_items:
    if os.path.exists(path):
        (os.remove or shutil.rmtree)(path)
```

### 6. Pre-Release Final Check

```
[ ] .env has removed real keys (or has been cleared from git history)
[ ] .env.example has been updated and synchronized with actual configuration
[ ] data/ directory has been cleared (auto-initializes on first production startup)
[ ] All __pycache__ have been cleaned
[ ] web/.next/ has been rebuilt (production mode)
[ ] Test suite passes
[ ] debug in config/settings.yaml is set to false (production environment)
```
