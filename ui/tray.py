"""Системный трей с контекстным меню и состояниями иконки."""

from PyQt6.QtCore import QSize, QTimer, pyqtSignal, Qt
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon


class JarvisTray(QSystemTrayIcon):
    """Иконка в системном трее."""

    open_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    pause_requested = pyqtSignal()
    restart_requested = pyqtSignal()
    quit_requested = pyqtSignal()
    interview_toggle_requested = pyqtSignal()
    interview_setup_requested = pyqtSignal()
    rescan_requested = pyqtSignal()
    interview_live_requested = pyqtSignal()

    STATE_SLEEPING = "sleeping"
    STATE_LISTENING = "listening"
    STATE_SPEAKING = "speaking"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = self.STATE_SLEEPING
        self._pulse = 0.0
        self._paused = False
        self._interview_mode = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._pulse_icon)
        self._timer.start(100)

        self._build_menu()
        self.set_state(self.STATE_SLEEPING)
        self.activated.connect(self._on_activated)

    def _build_menu(self) -> None:
        menu = QMenu()

        open_action = QAction("Открыть", self)
        open_action.triggered.connect(self.open_requested.emit)
        menu.addAction(open_action)

        settings_action = QAction("Настройки", self)
        settings_action.triggered.connect(self.settings_requested.emit)
        menu.addAction(settings_action)

        menu.addSeparator()

        self._interview_action = QAction("Режим собеседования", self)
        self._interview_action.setCheckable(True)
        self._interview_action.triggered.connect(self.interview_toggle_requested.emit)
        menu.addAction(self._interview_action)

        profile_action = QAction("Профиль собеседования...", self)
        profile_action.triggered.connect(self.interview_setup_requested.emit)
        menu.addAction(profile_action)

        self._live_action = QAction("▶ LIVE — слушать созвон", self)
        self._live_action.triggered.connect(self.interview_live_requested.emit)
        menu.addAction(self._live_action)

        rescan_action = QAction("Сканировать компьютер...", self)
        rescan_action.triggered.connect(self.rescan_requested.emit)
        menu.addAction(rescan_action)

        menu.addSeparator()

        self._pause_action = QAction("Приостановить", self)
        self._pause_action.triggered.connect(self._toggle_pause)
        menu.addAction(self._pause_action)

        restart_action = QAction("Перезапустить", self)
        restart_action.triggered.connect(self.restart_requested.emit)
        menu.addAction(restart_action)

        menu.addSeparator()

        quit_action = QAction("Выход", self)
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self._pause_action.setText(
            "Возобновить" if self._paused else "Приостановить"
        )
        self.pause_requested.emit()

    def is_paused(self) -> bool:
        return self._paused

    def set_interview_mode(self, active: bool) -> None:
        self._interview_mode = active
        self._interview_action.setChecked(active)
        self._live_action.setEnabled(active)

    def set_interview_live(self, live: bool) -> None:
        self._live_action.setText(
            "■ Остановить LIVE" if live else "▶ LIVE — слушать созвон"
        )

    def is_interview_mode(self) -> bool:
        return self._interview_mode

    def set_state(self, state: str) -> None:
        self._state = state
        self._update_icon()

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.open_requested.emit()

    def _pulse_icon(self) -> None:
        if self._state == self.STATE_LISTENING:
            self._pulse += 0.2
            self._update_icon()
        elif self._state == self.STATE_SLEEPING:
            self._pulse = 0

    def _make_icon(self, color: QColor, pulse: float = 0.0) -> QIcon:
        size = 64
        pix = QPixmap(size, size)
        pix.fill(QColor(0, 0, 0, 0))

        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        r = size // 2 - 4
        if pulse > 0:
            glow = QColor(color)
            glow.setAlpha(int(80 + 60 * abs(math_sin(pulse))))
            painter.setBrush(glow)
            painter.setPen(Qt.PenStyle.NoPen)
            gr = int(r + 6 * abs(math_sin(pulse)))
            painter.drawEllipse(size // 2 - gr, size // 2 - gr, gr * 2, gr * 2)

        painter.setBrush(color)
        painter.drawEllipse(size // 2 - r, size // 2 - r, r * 2, r * 2)

        # Буква J
        painter.setPen(QColor(255, 255, 255))
        font = painter.font()
        font.setPixelSize(28)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "J")
        painter.end()

        return QIcon(pix)

    def _update_icon(self) -> None:
        colors = {
            self.STATE_SLEEPING: QColor(120, 120, 130),
            self.STATE_LISTENING: QColor(0, 140, 255),
            self.STATE_SPEAKING: QColor(0, 200, 100),
        }
        if self._interview_mode:
            color = QColor(180, 80, 220)  # фиолетовый — режим собеседования
        else:
            color = colors.get(self._state, QColor(120, 120, 130))
        pulse = self._pulse if self._state == self.STATE_LISTENING else 0
        self.setIcon(self._make_icon(color, pulse))


def math_sin(x: float) -> float:
    import math
    return math.sin(x)
