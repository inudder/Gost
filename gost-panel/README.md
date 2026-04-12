# GOST Panel

Локальная Windows-панель для мониторинга сервисов GOST и проверки SOCKS5-прокси.

## Стек

- Python 3.14
- FastAPI + Uvicorn
- Jinja2 + HTMX + Alpine.js + TailwindCSS
- SQLite

## Запуск

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
python -m app.main
```

Панель по умолчанию слушает `http://127.0.0.1:17777`.

Либо через PowerShell-скрипты:

```powershell
.\scripts\bootstrap.ps1
.\scripts\start-panel.ps1
```

`bootstrap.ps1` на этой машине намеренно игнорирует глобальный `pip` proxy config, чтобы корректно установить зависимости в `.venv`.
