"""Перетаскивание оверлеев мышью."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QWidget


class DraggableMixin:
    """Миксин: зажать ЛКМ и перетащить окно."""

    def _init_draggable(self) -> None:
        self._drag_offset = None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
        super().mousePressEvent(event)  # type: ignore

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)  # type: ignore

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)  # type: ignore


def position_overlay(widget: QWidget, position: str) -> None:
    """Позиционировать виджет по настройке."""
    from PyQt6.QtWidgets import QApplication

    screen = QApplication.primaryScreen()
    if not screen:
        return
    geo = screen.availableGeometry()
    m = 20
    w, h = widget.width(), widget.height()
    pos = position.lower().strip()

    if pos == "bottom-left":
        widget.move(geo.left() + m, geo.bottom() - h - m)
    elif pos == "top-right":
        widget.move(geo.right() - w - m, geo.top() + m)
    elif pos == "top-left":
        widget.move(geo.left() + m, geo.top() + m)
    else:  # bottom-right
        widget.move(geo.right() - w - m, geo.bottom() - h - m)
