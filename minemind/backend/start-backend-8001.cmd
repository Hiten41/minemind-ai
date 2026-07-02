@echo off
cd /d "%~dp0"
"C:\Users\DELL\AppData\Local\Programs\Python\Python313\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8001
