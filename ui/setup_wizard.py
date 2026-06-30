"""Мастер первоначальной настройки JARVIS."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config.settings import mark_setup_complete, save_env_value, settings
from core import autostart
from core.listener import Listener
from skills import app_launcher, steam_control


class SetupWizard(QDialog):
    """Пошаговый мастер настройки."""

    def __init__(self, speaker=None, parent=None):
        super().__init__(parent)
        self._speaker = speaker
        self.setWindowTitle("Настройка JARVIS")
        self.setFixedSize(520, 420)
        self.setStyleSheet("""
            QDialog { background: #12121f; color: #dde; }
            QLabel { color: #ccd; font-size: 13px; }
            QLabel#step_title { color: #00aaff; font-size: 18px; font-weight: bold; }
            QLineEdit {
                background: #1a1a2e; color: #eee; border: 1px solid #334;
                border-radius: 6px; padding: 8px; font-size: 13px;
            }
            QPushButton {
                background: #0f3460; color: #eee; border: none;
                border-radius: 6px; padding: 10px 20px; font-size: 13px;
            }
            QPushButton:hover { background: #1a5276; }
            QPushButton#primary { background: #0077cc; }
            QCheckBox { color: #ccd; font-size: 13px; }
        """)

        self._stack = QStackedWidget()
        self._build_steps()

        layout = QVBoxLayout(self)
        layout.addWidget(self._stack)

        nav = QHBoxLayout()
        self._back_btn = QPushButton("Назад")
        self._back_btn.clicked.connect(self._go_back)
        self._next_btn = QPushButton("Далее")
        self._next_btn.setObjectName("primary")
        self._next_btn.clicked.connect(self._go_next)
        nav.addWidget(self._back_btn)
        nav.addStretch()
        nav.addWidget(self._next_btn)
        layout.addLayout(nav)

        self._step = 0
        self._update_nav()

    def _build_steps(self) -> None:
        self._stack.addWidget(self._step_mic())
        self._stack.addWidget(self._step_anthropic())
        self._stack.addWidget(self._step_vosk())
        self._stack.addWidget(self._step_discover())
        self._stack.addWidget(self._step_autostart())
        self._stack.addWidget(self._step_voice_test())

    def _step_mic(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        title = QLabel("Шаг 1: Микрофон")
        title.setObjectName("step_title")
        layout.addWidget(title)
        layout.addWidget(QLabel("Проверим, что микрофон доступен."))
        self._mic_result = QLabel("Нажмите «Проверить»")
        layout.addWidget(self._mic_result)
        test_btn = QPushButton("Проверить микрофон")
        test_btn.clicked.connect(self._test_mic)
        layout.addWidget(test_btn)
        layout.addStretch()
        return w

    def _step_anthropic(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        title = QLabel("Шаг 2: Claude API")
        title.setObjectName("step_title")
        layout.addWidget(title)
        layout.addWidget(QLabel(
            "1. Зайдите на console.anthropic.com\n"
            "2. Создайте аккаунт → API Keys → Create Key\n"
            "3. Скопируйте ключ (начинается с sk-ant-...)\n\n"
            "Регистрация бесплатна, новым аккаунтам ~$5 trial-кредитов.\n"
            "После исчерпания — оплата по факту использования (pay-as-you-go).\n"
            "Без ключа JARVIS не сможет понимать команды и отвечать."
        ))
        self._anthropic_input = QLineEdit()
        self._anthropic_input.setText(settings.anthropic_api_key)
        self._anthropic_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self._anthropic_input)
        layout.addStretch()
        return w

    def _step_vosk(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        title = QLabel("Шаг 3: Wake word «Джарвис»")
        title.setObjectName("step_title")
        layout.addWidget(title)
        layout.addWidget(QLabel(
            "Wake word работает полностью офлайн через Vosk — без API-ключей.\n\n"
            "Скажите «Джарвис» в микрофон или нажмите Ctrl+J.\n"
            "Модель: vosk-model-small-ru-0.22 (уже есть в jarvis_assistant/)\n"
            "или положите в jarvis/models/"
        ))
        self._vosk_result = QLabel("Нажмите «Проверить»")
        layout.addWidget(self._vosk_result)
        test_btn = QPushButton("Проверить модель Vosk")
        test_btn.clicked.connect(self._test_vosk)
        layout.addWidget(test_btn)
        layout.addStretch()
        return w

    def _step_discover(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        title = QLabel("Шаг 4: Поиск приложений")
        title.setObjectName("step_title")
        layout.addWidget(title)
        self._discover_result = QLabel("Нажмите «Найти»")
        layout.addWidget(self._discover_result)
        find_btn = QPushButton("Найти приложения и Steam")
        find_btn.clicked.connect(self._discover)
        layout.addWidget(find_btn)
        layout.addStretch()
        return w

    def _step_autostart(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        title = QLabel("Шаг 5: Автозапуск")
        title.setObjectName("step_title")
        layout.addWidget(title)
        self._autostart_cb = QCheckBox("Запускать JARVIS при старте Windows")
        self._autostart_cb.setChecked(settings.autostart)
        layout.addWidget(self._autostart_cb)
        layout.addStretch()
        return w

    def _step_voice_test(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        title = QLabel("Шаг 6: Тест голоса")
        title.setObjectName("step_title")
        layout.addWidget(title)
        layout.addWidget(QLabel("JARVIS произнесёт приветствие."))
        test_btn = QPushButton("Произнести приветствие")
        test_btn.clicked.connect(self._test_voice)
        layout.addWidget(test_btn)
        layout.addStretch()
        return w

    def _test_vosk(self) -> None:
        from core.vosk_stt import get_model_path, is_available

        if is_available():
            self._vosk_result.setText(f"✓ Модель найдена: {get_model_path()}")
        else:
            self._vosk_result.setText(
                "✗ Модель не найдена. Скачайте vosk-model-small-ru-0.22 "
                "с alphacephei.com/vosk/models"
            )

    def _test_mic(self) -> None:
        ok, msg = Listener.test_microphone()
        self._mic_result.setText(f"{'✓' if ok else '✗'} {msg}")

    def _discover(self) -> None:
        apps = app_launcher.discover_apps()
        steam = steam_control.get_steam_info()
        found = sum(1 for v in apps.values() if v.get("path"))
        self._discover_result.setText(f"Найдено приложений: {found}. {steam}")

    def _test_voice(self) -> None:
        if self._speaker:
            self._speaker.say_cached("welcome")

    def _go_back(self) -> None:
        if self._step > 0:
            self._step -= 1
            self._stack.setCurrentIndex(self._step)
            self._update_nav()

    def _go_next(self) -> None:
        if self._step == 1:
            key = self._anthropic_input.text().strip()
            if key:
                save_env_value("ANTHROPIC_API_KEY", key)
        elif self._step == 2:
            pass  # Vosk — проверка на шаге, ключ не нужен
        elif self._step == 4:
            if self._autostart_cb.isChecked():
                autostart.enable_autostart()
            else:
                autostart.disable_autostart()
        elif self._step == 5:
            self._finish()
            return

        if self._step < self._stack.count() - 1:
            self._step += 1
            self._stack.setCurrentIndex(self._step)
        self._update_nav()

    def _update_nav(self) -> None:
        self._back_btn.setEnabled(self._step > 0)
        self._next_btn.setText(
            "Завершить" if self._step == self._stack.count() - 1 else "Далее"
        )

    def _finish(self) -> None:
        mark_setup_complete()
        QMessageBox.information(
            self, "Готово", "JARVIS настроен и готов к работе!"
        )
        self.accept()
