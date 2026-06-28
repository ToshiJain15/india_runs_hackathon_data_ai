@echo off
echo ============================================================
echo  Redrob AI Candidate Ranker — Starting Server
echo ============================================================
echo.
echo  Dashboard:   http://127.0.0.1:8000/
echo  Rankings:    http://127.0.0.1:8000/results/
echo  Analytics:   http://127.0.0.1:8000/analytics/
echo  Admin:       http://127.0.0.1:8000/admin/
echo.
echo  Press Ctrl+C to stop.
echo.
C:\Python314\python.exe manage.py runserver 8000
