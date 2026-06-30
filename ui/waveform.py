"""Анимированная waveform, реагирующая на уровень звука."""

import math
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget


class WaveformWidget(QWidget):
    """Визуализация звуковой волны."""

    BARS = 24
    COLOR_ACTIVE = QColor(0, 180, 255)
    COLOR_IDLE = QColor(60, 60, 80)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = 0.0
        self._active = False
        self._phase = 0.0
        self._bar_heights = [0.1] * self.BARS

        self.setFixedSize(200, 40)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(50)

    def set_level(self, level: float) -> None:
        """Установить уровень звука (0-3000+)."""
        self._level = min(level / 1500.0, 1.0)

    def set_active(self, active: bool) -> None:
        self._active = active

    def _animate(self) -> None:
        self._phase += 0.15
        target = self._level if self._active else 0.05

        for i in range(self.BARS):
            wave = math.sin(self._phase + i * 0.4) * 0.3 + 0.5
            desired = target * wave if self._active else 0.08
            self._bar_heights[i] += (desired - self._bar_heights[i]) * 0.3

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        bar_w = w / (self.BARS * 2)
        gap = bar_w * 0.5

        for i, bh in enumerate(self._bar_heights):
            x = i * (bar_w + gap) + gap
            bar_h = max(3, bh * h * 0.9)
            y = (h - bar_h) / 2

            color = self.COLOR_ACTIVE if self._active else self.COLOR_IDLE
            alpha = int(150 + bh * 105)
            color.setAlpha(min(255, alpha))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(int(x), int(y), int(bar_w), int(bar_h), 2, 2)

        painter.end()
