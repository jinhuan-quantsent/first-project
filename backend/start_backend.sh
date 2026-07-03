#!/bin/bash
cd /opt/fund-sentiment/v5-deploy/backend
pkill -9 -f 'uvicorn app.main' 2>/dev/null
sleep 2
nohup /opt/fund-sentiment/v5-deploy/backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 > app.log 2>&1 &
disown
sleep 3
curl -s http://localhost:8000/health || echo "health check failed"
