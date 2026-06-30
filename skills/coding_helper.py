"""Помощь с кодом и запуск IDE."""

from config.settings import LAST_CODE_PATH, log
from skills.app_launcher import launch_app


def open_ide(ide_name: str) -> str:
    """Открыть Cursor, VS Code или PyCharm."""
    mapping = {
        "cursor": "cursor",
        "курсор": "cursor",
        "vscode": "vscode",
        "vs code": "vscode",
        "code": "vscode",
        "pycharm": "pycharm",
        "пайчарм": "pycharm",
    }
    key = ide_name.lower().strip()
    app = mapping.get(key, key)
    return launch_app(app)


def save_code(code: str, language: str = "python") -> None:
    """Сохранить последний ответ с кодом."""
    if not code:
        return
    try:
        ext = {"python": ".py", "javascript": ".js", "html": ".html",
               "css": ".css", "sql": ".sql", "bash": ".sh"}.get(language, ".txt")
        path = LAST_CODE_PATH.parent / f"last_code{ext}"
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        log.info("Код сохранён: %s", path)
    except Exception as e:
        log.error("save_code: %s", e)
