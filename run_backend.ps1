# Chạy Backend API từ thư mục gốc dự án
Set-Location $PSScriptRoot
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
