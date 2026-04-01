@echo off
echo Starting backend and frontend...
start "Backend" cmd /k ".venv\Scripts\activate.bat && python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"
start "Frontend" cmd /k ".venv\Scripts\activate.bat && streamlit run frontend/app.py"
