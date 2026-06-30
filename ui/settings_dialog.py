"""Окно настроек JARVIS (не только первый запуск)."""

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config.settings import reload_settings, save_env_value, settings
from core import autostart


VOICES = [
    ("ru-RU-DmitryNeural", "Дмитрий — взрослый мужской (рекомендуется)"),
    ("ru-RU-SvetlanaNeural", "Светлана — женский"),
    ("ru-RU-DariyaNeural", "Дария — женский, официальный"),
]

TITLES = ["сэр", "мэм", "мисс"]
POSITIONS = [
    ("bottom-right", "Правый нижний"),
    ("bottom-left", "Левый нижний"),
    ("top-right", "Правый верхний"),
    ("top-left", "Левый верхний"),
]


class SettingsDialog(QDialog):
    """Настройки: API, голос, обращение, оверлей, автозапуск."""

    def __init__(self, speaker=None, parent=None):
        super().__init__(parent)
        self._speaker = speaker
        self.setWindowTitle("Настройки JARVIS")
        self.setMinimumSize(520, 460)
        self.setStyleSheet("""
            QDialog { background: #12121f; color: #dde; }
            QLabel { color: #ccd; }
            QLineEdit, QComboBox {
                background: #1a1a2e; color: #eee; border: 1px solid #334;
                border-radius: 6px; padding: 8px;
            }
            QPushButton {
                background: #0f3460; color: #eee; border: none;
                border-radius: 6px; padding: 10px 18px;
            }
            QPushButton:hover { background: #1a5276; }
            QTabWidget::pane { border: 1px solid #334; }
            QTabBar::tab { background: #1a1a2e; color: #99a; padding: 8px 14px; }
            QTabBar::tab:selected { background: #0f3460; color: #fff; }
            QCheckBox { color: #ccd; }
        """)

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._tab_api(), "API ключи")
        tabs.addTab(self._tab_voice(), "Голос и тон")
        tabs.addTab(self._tab_ui(), "Интерфейс")
        tabs.addTab(self._tab_system(), "Система")
        layout.addWidget(tabs)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Сохранить")
        save.clicked.connect(self._save)
        btns.addWidget(cancel)
        btns.addWidget(save)
        layout.addLayout(btns)

    def _tab_api(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self._groq = QLineEdit(getattr(settings, "groq_api_key", ""))
        self._groq.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("GROQ_API_KEY (собесы):", self._groq)
        groq_hint = QLabel(
            "Бесплатно: console.groq.com → API Keys → Create.\n"
            "Нужен для режима собеседования (Ctrl+Shift+L)."
        )
        groq_hint.setStyleSheet("color: #778; font-size: 11px;")
        form.addRow(groq_hint)

        ollama_hint = QLabel(
            "Код: Ollama локально (ollama.com).\n"
            "После установки: ollama pull qwen2.5-coder:7b\n"
            "Ollama должна быть запущена при старте JARVIS."
        )
        ollama_hint.setStyleSheet("color: #778; font-size: 11px;")
        form.addRow(ollama_hint)

        self._anthropic = QLineEdit(settings.anthropic_api_key)
        self._anthropic.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("ANTHROPIC_API_KEY (опционально):", self._anthropic)
        hint = QLabel("Claude — только если переключите провайдер на anthropic в .env")
        hint.setStyleSheet("color: #778; font-size: 11px;")
        form.addRow(hint)
        return w

    def _tab_voice(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._voice = QComboBox()
        for vid, label in VOICES:
            self._voice.addItem(label, vid)
        idx = next((i for i, (v, _) in enumerate(VOICES) if v == settings.tts_voice), 0)
        self._voice.setCurrentIndex(idx)

        self._title = QComboBox()
        self._title.addItems(TITLES)
        ti = TITLES.index(settings.user_title) if settings.user_title in TITLES else 0
        self._title.setCurrentIndex(ti)

        form.addRow("Голос TTS:", self._voice)
        form.addRow("Обращение:", self._title)
        desc = QLabel(
            "Джарвис — взрослый вежливый дворецкий.\n"
            "Говорит на «Вы», спокойно и уважительно."
        )
        desc.setStyleSheet("color: #8899aa; font-size: 11px;")
        form.addRow(desc)

        test_btn = QPushButton("Прослушать приветствие")
        test_btn.clicked.connect(self._test_voice)
        form.addRow(test_btn)
        return w

    def _tab_ui(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._position = QComboBox()
        for pid, label in POSITIONS:
            self._position.addItem(label, pid)
        pi = next(
            (i for i, (p, _) in enumerate(POSITIONS) if p == settings.overlay_position), 0
        )
        self._position.setCurrentIndex(pi)
        form.addRow("Позиция оверлея:", self._position)
        form.addRow(QLabel("Оверлей можно перетаскивать мышью."))
        return w

    def _tab_system(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._autostart = QCheckBox("Запускать при старте Windows")
        self._autostart.setChecked(autostart.is_autostart_enabled())
        form.addRow(self._autostart)
        return w

    def _test_voice(self) -> None:
        if self._speaker:
            self._speaker.set_title(self._title.currentText())
            self._speaker.say_cached("greeting", block=True)

    def _save(self) -> None:
        save_env_value("GROQ_API_KEY", self._groq.text().strip())
        save_env_value("ANTHROPIC_API_KEY", self._anthropic.text().strip())
        save_env_value("TTS_VOICE", self._voice.currentData())
        save_env_value("USER_TITLE", self._title.currentText())
        save_env_value("OVERLAY_POSITION", self._position.currentData())
        reload_settings()

        if self._autostart.isChecked():
            autostart.enable_autostart()
        else:
            autostart.disable_autostart()

        if self._speaker:
            self._speaker.set_title(settings.user_title)

        QMessageBox.information(self, "Сохранено", "Настройки применены.")
        self.accept()
