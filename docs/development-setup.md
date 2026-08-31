# Gate 2 development setup

This setup covers only the repository and configuration foundation. It does not
connect to PostgreSQL or WordPress and performs no network calls to `ehsmall.com`.

## Windows PowerShell

From the repository root:

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install --upgrade pip
backend/.venv/Scripts/python.exe -m pip install -e "backend[dev]"
backend/.venv/Scripts/python.exe -m ruff format --check backend
backend/.venv/Scripts/python.exe -m ruff check backend
backend/.venv/Scripts/python.exe -m mypy backend/app backend/tests
backend/.venv/Scripts/python.exe -m pytest backend/tests
backend/.venv/Scripts/python.exe -c "from app.main import app; print(app.title, app.version)"
```

To run the local foundation from `backend/`:

```powershell
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Copy `backend/.env.example` to `backend/.env` only when local overrides are
needed. Never commit `.env`, database credentials, WordPress configuration, or
site archives.
