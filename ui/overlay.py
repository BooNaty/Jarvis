"""Тёмный оверлей в правом нижнем углу экрана."""

import math

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config.settings import settings
from ui.draggable import DraggableMixin, position_overlay
from ui.waveform import WaveformWidget

# Состояния ассистента
STATE_SLEEPING = "sleeping"
STATE_LISTENING = "listening"
STATE_THINKING = "thinking"
STATE_SPEAKING = "speaking"

STATUS_TEXT = {
    STATE_SLEEPING: "Спит",
    STATE_LISTENING: "Слушаю...",
    STATE_THINKING: "Думаю...",
    STATE_SPEAKING: "Говорю...",
}


class PulseIcon(QWidget):
    """Круглая пульсирующая иконка J."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(48, 48)
        self._pulse = 0.0
        self._active = False
        self._state = STATE_SLEEPING

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(50)

    def set_state(self, state: str) -> None:
        self._state = state
        self._active = state != STATE_SLEEPING

    def _animate(self) -> None:
        if self._active:
            self._pulse += 0.12
        else:
            self._pulse *= 0.9
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        colors = {
            STATE_SLEEPING: QColor(80, 80, 100),
            STATE_LISTENING: QColor(0, 160, 255),
            STATE_THINKING: QColor(255, 180, 0),
            STATE_SPEAKING: QColor(0, 210, 110),
        }
        color = colors.get(self._state, QColor(80, 80, 100))

        cx, cy = self.width() // 2, self.height() // 2
        r = 18

        if self._active:
            glow_r = r + 4 * abs(math.sin(self._pulse))
            glow = QColor(color)
            glow.setAlpha(60)
            painter.setBrush(glow)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(
                int(cx - glow_r), int(cy - glow_r),
                int(glow_r * 2), int(glow_r * 2),
            )

        painter.setBrush(color)
        painter.drawEllipse(cx - r, cy - r, r * 2, r * 2)

        painter.setPen(QColor(255, 255, 255))
        font = painter.font()
        font.setPixelSize(20)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "J")
        painter.end()


class CodePanel(QFrame):
    """Всплывающая панель с кодом и кнопкой копирования."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setStyleSheet("""
            QFrame {
                background: #1a1a2e;
                border: 1px solid #0f3460;
                border-radius: 12px;
            }
            QTextEdit {
                background: #0d1117;
                color: #c9d1d9;
                border: none;
                border-radius: 8px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                padding: 8px;
            }
            QPushButton {
                background: #0f3460;
                color: #e0e0e0;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
            }
            QPushButton:hover { background: #1a5276; }
            QLabel { color: #8899aa; font-size: 11px; }
        """)
        self.setFixedSize(500, 350)
        self.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        header = QLabel("Ответ с кодом")
        layout.addWidget(header)

        self._code_edit = QTextEdit()
        self._code_edit.setReadOnly(True)
        layout.addWidget(self._code_edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        copy_btn = QPushButton("Копировать")
        copy_btn.clicked.connect(self._copy)
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.hide)
        btn_row.addWidget(copy_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def show_code(self, code: str, language: str = "python") -> None:
        self._code_edit.setPlainText(code)
        self._apply_highlight(language)
        self.show()
        self.raise_()

    def _apply_highlight(self, language: str) -> None:
        """Простая подсветка синтаксиса через HTML."""
        code = self._code_edit.toPlainText()
        if language == "python":
            import html
            escaped = html.escape(code)
            # Ключевые слова
            keywords = [
                "def", "class", "import", "from", "return", "if", "else",
                "elif", "for", "while", "try", "except", "with", "as",
                "True", "False", "None", "and", "or", "not", "in",
            ]
            for kw in keywords:
                escaped = escaped.replace(
                    f" {kw} ", f' <span style="color:#ff7b72;"> {kw} </span> '
                )
            self._code_edit.setHtml(
                f'<pre style="color:#c9d1d9;">{escaped}</pre>'
            )

    def _copy(self) -> None:
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._code_edit.toPlainText())


class OverlayWindow(DraggableMixin, QWidget):
    """Главное окно оверлея."""

    def __init__(self):
        super().__init__()
        self._init_draggable()
        self._state = STATE_SLEEPING

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(280, 160)

        self._build_ui()
        self.apply_position()

    def apply_position(self) -> None:
        position_overlay(self, settings.overlay_position)

    def _build_ui(self) -> None:
        container = QFrame(self)
        container.setGeometry(0, 0, 280, 160)
        container.setStyleSheet("""
            QFrame {
                background: rgba(15, 15, 25, 220);
                border: 1px solid rgba(60, 80, 120, 120);
                border-radius: 16px;
            }
            QLabel#status {
                color: #6688aa;
                font-size: 11px;
            }
            QLabel#command {
                color: #ccddee;
                font-size: 12px;
            }
            QLabel#title {
                color: #00aaff;
                font-size: 14px;
                font-weight: bold;
            }
        """)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 12, 16, 12)

        top = QHBoxLayout()
        self._icon = PulseIcon()
        top.addWidget(self._icon)

        title_col = QVBoxLayout()
        title = QLabel("JARVIS")
        title.setObjectName("title")
        self._status_label = QLabel(STATUS_TEXT[STATE_SLEEPING])
        self._status_label.setObjectName("status")
        title_col.addWidget(title)
        title_col.addWidget(self._status_label)
        top.addLayout(title_col)
        top.addStretch()
        layout.addLayout(top)

        self._waveform = WaveformWidget()
        layout.addWidget(self._waveform, alignment=Qt.AlignmentFlag.AlignCenter)

        self._command_label = QLabel("")
        self._command_label.setObjectName("command")
        self._command_label.setWordWrap(True)
        self._command_label.setMaximumHeight(40)
        layout.addWidget(self._command_label)

        # Панель кода (отдельное окно)
        self._code_panel = CodePanel()

    def set_state(self, state: str) -> None:
        self._state = state
        self._status_label.setText(STATUS_TEXT.get(state, state))
        self._icon.set_state(state)
        self._waveform.set_active(state in (STATE_LISTENING, STATE_SPEAKING))

    def set_command_text(self, text: str) -> None:
        self._command_label.setText(text)

    def set_audio_level(self, level: float) -> None:
        self._waveform.set_level(level)

    def show_code(self, code: str, language: str = "python") -> None:
        # Позиционировать панель над оверлеем
        self._code_panel.move(
            self.x() - 220,
            self.y() - self._code_panel.height() - 10,
        )
        self._code_panel.show_code(code, language)

    def show_overlay(self) -> None:
        self.show()
        self.raise_()

    def hide_overlay(self) -> None:
        self.hide()
