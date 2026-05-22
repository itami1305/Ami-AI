# Chạy Win App với auto-reload (mô phỏng uvicorn --reload).
# Muốn chạy 1 lần không reload: python -m app.main  (hoặc thêm cờ --no-watch).
Set-Location $PSScriptRoot
python -m app.dev_reload @args
