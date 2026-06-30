"""Невидимый при шеринге оверлей для режима собеседования."""

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config.settings import settings
from ui.draggable import DraggableMixin, position_overlay
from utils.win_capture import apply_to_qt_window

STATE_IDLE = "idle"
STATE_LISTENING = "listening"
STATE_THINKING = "thinking"
STATE_STREAMING = "streaming"
STATE_ANSWER = "answer"
STATE_LIVE = "live"
STATE_PREP = "prep"

STATUS_LABELS = {
    STATE_PREP: "● Подготовка — Ctrl+Shift+L когда созвон начнётся",
    STATE_IDLE: "● Готов — Ctrl+Shift+L для LIVE",
    STATE_LIVE: "● LIVE — слушаю Zoom / Meet / Teams...",
    STATE_LISTENING: "● Слушаю микрофон...",
    STATE_THINKING: "● Думаю...",
    STATE_STREAMING: "● Пишу ответ...",
    STATE_ANSWER: "● Ответ готов — жду следующий вопрос",
}


class InterviewOverlay(DraggableMixin, QWidget):
    """
    Призрачная панель: видна только вам,
    не попадает в Zoom / Teams / OBS при шеринге экрана.
    """

    # Сигналы для потокобезопасного обновления из фонового потока
    _sig_chunk = pyqtSignal(str)
    _sig_done = pyqtSignal()
    _sig_question = pyqtSignal(str)
    _sig_state = pyqtSignal(str)

    WIDTH = 440
    HEIGHT = 360

    def __init__(self):
        super().__init__()
        self._init_draggable()
        self._state = STATE_IDLE
        self._answer_buffer = ""

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WIDTH, self.HEIGHT)

        self._build_ui()
        position_overlay(self, "top-right")

        self._sig_chunk.connect(self._on_chunk)
        self._sig_done.connect(self._on_stream_done)
        self._sig_question.connect(self._on_question)
        self._sig_state.connect(self.set_state)

        QTimer.singleShot(100, self._apply_capture_exclusion)

    def _build_ui(self) -> None:
        container = QFrame(self)
        container.setGeometry(0, 0, self.WIDTH, self.HEIGHT)
        container.setStyleSheet("""
            QFrame {
                background: rgba(8, 10, 18, 242);
                border: 1px solid rgba(60, 100, 160, 120);
                border-radius: 10px;
            }
            QLabel#header { color: #5588bb; font-size: 10px; font-weight: bold; }
            QLabel#status { color: #44aa66; font-size: 10px; }
            QLabel#question_label { color: #778899; font-size: 10px; }
            QLabel#question { color: #99bbcc; font-size: 11px; }
            QLabel#answer { color: #f0f4f8; font-size: 13px; }
            QLabel#lang { color: #6688aa; font-size: 9px; }
        """)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(5)

        header = QLabel("JARVIS · Собеседование (только для Вас)")
        header.setObjectName("header")
        layout.addWidget(header)

        self._status = QLabel(STATUS_LABELS[STATE_IDLE])
        self._status.setObjectName("status")
        layout.addWidget(self._status)

        self._lang_label = QLabel("")
        self._lang_label.setObjectName("lang")
        layout.addWidget(self._lang_label)

        self._prep_hint = QLabel(
            "1. Заполните профиль  2. Наденьте наушники  3. Ctrl+Shift+L когда созвон начался"
        )
        self._prep_hint.setStyleSheet("color: #aa8844; font-size: 9px;")
        self._prep_hint.setWordWrap(True)
        layout.addWidget(self._prep_hint)

        layout.addWidget(QLabel("Вопрос:"))
        self._question = QLabel("—")
        self._question.setObjectName("question")
        self._question.setWordWrap(True)
        layout.addWidget(self._question)

        layout.addWidget(QLabel("Ответ:"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._answer = QLabel("Ожидаю вопрос...")
        self._answer.setObjectName("answer")
        self._answer.setWordWrap(True)
        self._answer.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._answer.setFont(QFont("Segoe UI", 12))
        scroll.setWidget(self._answer)
        layout.addWidget(scroll, stretch=1)

        hint = QLabel(
            "Ctrl+Shift+L — LIVE (звук созвона)  |  Ctrl+Shift+V — буфер  |  Ctrl+Shift+I — микрофон"
        )
        hint.setStyleSheet("color: #445566; font-size: 9px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._scroll = scroll

    def _apply_capture_exclusion(self) -> None:
        ok = apply_to_qt_window(self, exclude=True)
        if not ok:
            self._status.setText("● Готов (защита экрана: Win10 2004+)")

    def show_panel(self) -> None:
        self.show()
        self.raise_()
        QTimer.singleShot(50, self._apply_capture_exclusion)

    def hide_panel(self) -> None:
        self.hide()

    def set_state(self, state: str) -> None:
        self._state = state
        self._status.setText(STATUS_LABELS.get(state, state))
        colors = {
            STATE_PREP: "#aa8844",
            STATE_IDLE: "#44aa66",
            STATE_LIVE: "#ff4466",
            STATE_LISTENING: "#00aaff",
            STATE_THINKING: "#ffaa00",
            STATE_STREAMING: "#00ccff",
            STATE_ANSWER: "#44dd88",
        }
        self._status.setStyleSheet(f"color: {colors.get(state, '#44aa66')}; font-size: 10px;")

    def set_prep_mode(self, prep: bool) -> None:
        """Режим подготовки до начала созвона."""
        self._prep_hint.setVisible(prep)
        if prep:
            self.set_state(STATE_PREP)

    def set_audio_level(self, level: float) -> None:
        """Уровень звука созвона (для будущей визуализации)."""
        pass

    def show_question(self, text: str) -> None:
        self._sig_question.emit(text)

    def _on_question(self, text: str) -> None:
        self._question.setText(text or "—")

    def set_answer_language(self, lang: str) -> None:
        label = {"ru": "🇷🇺 Ответ на русском", "en": "🇬🇧 Answer in English"}.get(lang, "")
        self._lang_label.setText(label)

    def start_streaming_answer(self) -> None:
        self._answer_buffer = ""
        self._answer.setText("")
        self.set_state(STATE_STREAMING)

    def append_answer_chunk(self, chunk: str) -> None:
        """Потокобезопасно из фонового потока."""
        self._sig_chunk.emit(chunk)

    def finish_streaming(self) -> None:
        self._sig_done.emit()

    def _on_chunk(self, chunk: str) -> None:
        self._answer_buffer += chunk
        self._answer.setText(self._answer_buffer)
        # Автоскролл вниз
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
        if self._state != STATE_STREAMING:
            self.set_state(STATE_STREAMING)

    def _on_stream_done(self) -> None:
        self.set_state(STATE_ANSWER)

    def show_answer(self, text: str) -> None:
        self._answer_buffer = text
        self._answer.setText(text or "Не удалось сформировать ответ.")
        self.set_state(STATE_ANSWER)

    def get_answer_text(self) -> str:
        return self._answer_buffer

    def clear(self) -> None:
        self._question.setText("—")
        self._answer.setText("Ожидаю вопрос...")
        self._lang_label.setText("")
        self._answer_buffer = ""
        self.set_state(STATE_PREP)
