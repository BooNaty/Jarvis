"""Редактор профиля для режима собеседования."""

import json

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config.settings import INTERVIEW_PROFILE_PATH, log


def load_interview_profile() -> dict:
    """Загрузить профиль собеседования."""
    if INTERVIEW_PROFILE_PATH.exists():
        try:
            with open(INTERVIEW_PROFILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            log.error("load_interview_profile: %s", e)
    return {
        "name": "",
        "position": "",
        "experience_years": "",
        "resume": "",
        "skills": "",
        "projects": "",
        "company_name": "",
        "company_info": "",
        "job_description": "",
        "interview_language": "auto",
        "answer_style": "concise",
        "notes": "",
    }


def save_interview_profile(profile: dict) -> None:
    """Сохранить профиль."""
    INTERVIEW_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(INTERVIEW_PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def profile_to_context(profile: dict) -> str:
    """Собрать текстовый контекст для Claude."""
    parts = []
    if profile.get("name"):
        parts.append(f"Имя кандидата: {profile['name']}")
    if profile.get("position"):
        parts.append(f"Позиция: {profile['position']}")
    if profile.get("experience_years"):
        parts.append(f"Опыт: {profile['experience_years']} лет")
    if profile.get("resume"):
        parts.append(f"Резюме:\n{profile['resume']}")
    if profile.get("skills"):
        parts.append(f"Навыки:\n{profile['skills']}")
    if profile.get("projects"):
        parts.append(f"Проекты:\n{profile['projects']}")
    if profile.get("company_name"):
        parts.append(f"Компания: {profile['company_name']}")
    if profile.get("company_info"):
        parts.append(f"О компании:\n{profile['company_info']}")
    if profile.get("job_description"):
        parts.append(f"Вакансия:\n{profile['job_description']}")
    if profile.get("notes"):
        parts.append(f"Заметки:\n{profile['notes']}")
    return "\n\n".join(parts)


class InterviewSetupDialog(QDialog):
    """Диалог настройки профиля перед собеседованием."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Профиль собеседования")
        self.setMinimumSize(560, 520)
        self.setStyleSheet("""
            QDialog { background: #12121f; color: #dde; }
            QLabel { color: #bbc; font-size: 12px; }
            QLineEdit, QTextEdit, QComboBox {
                background: #1a1a2e; color: #eee;
                border: 1px solid #334; border-radius: 4px; padding: 6px;
            }
            QTabWidget::pane { border: 1px solid #334; }
            QTabBar::tab {
                background: #1a1a2e; color: #99a; padding: 8px 14px;
            }
            QTabBar::tab:selected { background: #0f3460; color: #fff; }
            QPushButton {
                background: #0f3460; color: #eee; border: none;
                border-radius: 6px; padding: 10px 20px;
            }
            QPushButton:hover { background: #1a5276; }
        """)

        self._profile = load_interview_profile()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        info = QLabel(
            "Заполните данные о себе и вакансии.\n\n"
            "На собеседовании:\n"
            "• Наденьте наушники (JARVIS слышит звук из Zoom/Meet/Teams)\n"
            "• Ctrl+Shift+L — LIVE режим (автослушание рекрутера)\n"
            "• Ответы появятся в невидимой панели (рекрутер не увидит)"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        tabs = QTabWidget()

        # Вкладка: о себе
        about = QWidget()
        about_form = QFormLayout(about)
        self._name = QLineEdit(self._profile.get("name", ""))
        self._position = QLineEdit(self._profile.get("position", ""))
        self._experience = QLineEdit(self._profile.get("experience_years", ""))
        self._resume = QTextEdit()
        self._resume.setPlainText(self._profile.get("resume", ""))
        self._resume.setPlaceholderText("Краткое резюме, опыт работы...")
        self._resume.setMaximumHeight(120)
        self._skills = QTextEdit()
        self._skills.setPlainText(self._profile.get("skills", ""))
        self._skills.setPlaceholderText("Python, SQL, Docker...")
        self._skills.setMaximumHeight(80)
        self._projects = QTextEdit()
        self._projects.setPlainText(self._profile.get("projects", ""))
        self._projects.setPlaceholderText("Ключевые проекты и достижения...")
        self._projects.setMaximumHeight(100)

        about_form.addRow("Имя:", self._name)
        about_form.addRow("Позиция:", self._position)
        about_form.addRow("Опыт (лет):", self._experience)
        about_form.addRow("Резюме:", self._resume)
        about_form.addRow("Навыки:", self._skills)
        about_form.addRow("Проекты:", self._projects)
        tabs.addTab(about, "О себе")

        # Вкладка: компания
        company = QWidget()
        company_form = QFormLayout(company)
        self._company_name = QLineEdit(self._profile.get("company_name", ""))
        self._company_info = QTextEdit()
        self._company_info.setPlainText(self._profile.get("company_info", ""))
        self._company_info.setPlaceholderText("Чем занимается компания, культура, стек...")
        self._job_desc = QTextEdit()
        self._job_desc.setPlainText(self._profile.get("job_description", ""))
        self._job_desc.setPlaceholderText("Текст вакансии или требования...")

        company_form.addRow("Компания:", self._company_name)
        company_form.addRow("О компании:", self._company_info)
        company_form.addRow("Вакансия:", self._job_desc)
        tabs.addTab(company, "Компания")

        # Вкладка: настройки
        opts = QWidget()
        opts_form = QFormLayout(opts)
        self._language = QComboBox()
        self._language.addItems([
            "auto — Авто (по языку вопроса)",
            "ru — Русский",
            "en — English",
        ])
        lang = self._profile.get("interview_language", "auto")
        lang_idx = {"auto": 0, "ru": 1, "en": 2}.get(lang, 0)
        self._language.setCurrentIndex(lang_idx)

        self._style = QComboBox()
        self._style.addItems(["concise — Кратко (3-4 предложения)", "detailed — Подробно"])
        style = self._profile.get("answer_style", "concise")
        self._style.setCurrentIndex(0 if style == "concise" else 1)

        self._notes = QTextEdit()
        self._notes.setPlainText(self._profile.get("notes", ""))
        self._notes.setPlaceholderText("Что подчеркнуть, чего избегать, зарплатные ожидания...")

        opts_form.addRow("Язык ответов:", self._language)
        opts_form.addRow("Стиль:", self._style)
        opts_form.addRow("Заметки:", self._notes)
        tabs.addTab(opts, "Настройки")

        layout.addWidget(tabs)

        buttons = QHBoxLayout()
        buttons.addStretch()
        save_btn = QPushButton("Сохранить")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)

    def _save(self) -> None:
        profile = {
            "name": self._name.text().strip(),
            "position": self._position.text().strip(),
            "experience_years": self._experience.text().strip(),
            "resume": self._resume.toPlainText().strip(),
            "skills": self._skills.toPlainText().strip(),
            "projects": self._projects.toPlainText().strip(),
            "company_name": self._company_name.text().strip(),
            "company_info": self._company_info.toPlainText().strip(),
            "job_description": self._job_desc.toPlainText().strip(),
            "interview_language": ["auto", "ru", "en"][self._language.currentIndex()],
            "answer_style": "concise" if self._style.currentIndex() == 0 else "detailed",
            "notes": self._notes.toPlainText().strip(),
        }
        if not profile["resume"] and not profile["skills"]:
            QMessageBox.warning(
                self, "Внимание",
                "Заполните хотя бы резюме или навыки — иначе ответы будут общими.",
            )
        save_interview_profile(profile)
        self._profile = profile
        self.accept()

    def get_profile(self) -> dict:
        return self._profile
