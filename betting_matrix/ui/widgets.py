"""Composants d'interface reutilisables."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QUrl, QSize
from PyQt6.QtGui import QPixmap, QColor, QPainter
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..theme import (
    ACCENT,
    AMBER,
    BG_DEEP,
    BLUE,
    BORDER,
    BORDER_SOFT,
    CARD,
    CARD_ALT,
    MUTED,
    PURPLE,
    RED,
    TEXT,
    TEXT_SOFT,
)

# --------------------------------------------------------------- images async

_manager: QNetworkAccessManager | None = None
_pixmap_cache: dict[tuple[str, int], QPixmap] = {}
_pending: dict[str, list[tuple[QLabel, int]]] = {}


def _on_image_loaded(reply, url: str) -> None:
    try:
        data = bytes(reply.readAll())
        pixmap = QPixmap()
        if data:
            pixmap.loadFromData(data)
        if not pixmap.isNull():
            for label, size in _pending.pop(url, []):
                try:
                    _pixmap_cache[(url, size)] = pixmap.scaled(
                        size,
                        size,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    label.setPixmap(_pixmap_cache[(url, size)])
                except RuntimeError:
                    continue
        else:
            _pending.pop(url, None)
    finally:
        reply.deleteLater()


def load_image(label: QLabel, url: str, size: int = 24) -> None:
    """Charge un logo distant en arriere-plan (thread GUI, sans bloquer)."""
    global _manager
    if not url:
        label.clear()
        return
    cached = _pixmap_cache.get((url, size))
    if cached is not None:
        label.setPixmap(cached)
        return
    _pending.setdefault(url, []).append((label, size))
    if _manager is None:
        _manager = QNetworkAccessManager()
    request = QNetworkRequest(QUrl(url))
    request.setAttribute(
        QNetworkRequest.Attribute.CacheLoadControlAttribute,
        QNetworkRequest.CacheLoadControl.PreferCache,
    )
    reply = _manager.get(request)
    reply.finished.connect(lambda r=reply, u=url: _on_image_loaded(r, u))


class LogoLabel(QLabel):
    def __init__(self, url: str = "", size: int = 24, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background: transparent;")
        if url:
            load_image(self, url, size)


class TeamBadge(QWidget):
    """Logo + nom d'equipe sur une ligne."""

    def __init__(self, name: str, logo_url: str = "", size: int = 20, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(LogoLabel(logo_url, size))
        self.name_label = QLabel(name)
        self.name_label.setStyleSheet(f"color: {TEXT}; font-weight: 600;")
        row.addWidget(self.name_label)
        row.addStretch()

    def set_name(self, name: str) -> None:
        self.name_label.setText(name)


# --------------------------------------------------------------------- cards


class Card(QFrame):
    def __init__(
        self,
        title: str | None = None,
        subtitle: str | None = None,
        padding: int = 18,
        spacing: int = 10,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(padding, padding, padding, padding)
        outer.setSpacing(spacing)
        self.header = QHBoxLayout()
        self.header.setSpacing(8)
        self.title_label: QLabel | None = None
        self.subtitle_label: QLabel | None = None
        if title:
            title_box = QVBoxLayout()
            title_box.setSpacing(1)
            self.title_label = QLabel(title)
            self.title_label.setObjectName("cardTitle")
            title_box.addWidget(self.title_label)
            if subtitle:
                self.subtitle_label = QLabel(subtitle)
                self.subtitle_label.setObjectName("small")
                title_box.addWidget(self.subtitle_label)
            self.header.addLayout(title_box)
            self.header.addStretch()
            outer.addLayout(self.header)
        self.body = QVBoxLayout()
        self.body.setSpacing(spacing)
        outer.addLayout(self.body, 1)

    def add(self, widget: QWidget, stretch: int = 0) -> None:
        self.body.addWidget(widget, stretch)

    def add_layout(self, layout, stretch: int = 0) -> None:
        self.body.addLayout(layout, stretch)

    def add_header_widget(self, widget: QWidget) -> None:
        self.header.addWidget(widget)


class StatCard(QFrame):
    def __init__(
        self,
        title: str,
        value: str = "—",
        hint: str = "",
        accent: str = ACCENT,
        symbol: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("card")
        self._accent = accent
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        if symbol:
            icon = QLabel(symbol)
            icon.setFixedSize(26, 26)
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon.setStyleSheet(
                f"background: {CARD_ALT}; color: {accent}; border-radius: 8px; "
                f"font-size: 12pt; font-weight: 700;"
            )
            top.addWidget(icon)
        title_label = QLabel(title.upper())
        title_label.setStyleSheet(
            f"color: {MUTED}; font-size: 8pt; font-weight: 700; letter-spacing: 1px;"
        )
        top.addWidget(title_label)
        top.addStretch()
        layout.addLayout(top)

        self.value_label = QLabel(value)
        self.value_label.setObjectName("valueBig")
        self.value_label.setStyleSheet(f"color: {accent};")
        layout.addWidget(self.value_label)

        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("small")
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)
        self.setMinimumWidth(150)

    def set_value(self, value: str, hint: str | None = None, accent: str | None = None) -> None:
        self.value_label.setText(value)
        if hint is not None:
            self.hint_label.setText(hint)
        if accent:
            self._accent = accent
            self.value_label.setStyleSheet(f"color: {accent};")


class Badge(QLabel):
    KINDS = {
        "green": (ACCENT, "rgba(40,209,124,0.13)"),
        "red": (RED, "rgba(242,99,114,0.13)"),
        "amber": (AMBER, "rgba(244,183,64,0.13)"),
        "blue": (BLUE, "rgba(76,141,255,0.13)"),
        "purple": (PURPLE, "rgba(167,139,250,0.13)"),
        "gray": (MUTED, "rgba(130,149,176,0.12)"),
    }

    def __init__(self, text: str = "", kind: str = "gray", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_kind(kind)

    def set_kind(self, kind: str) -> None:
        color, background = self.KINDS.get(kind, self.KINDS["gray"])
        self.setStyleSheet(
            f"color: {color}; background: {background}; border-radius: 7px; "
            f"padding: 2px 8px; font-size: 8pt; font-weight: 700;"
        )


class FormBadges(QWidget):
    def __init__(self, form: str = "", parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(3)
        self.set_form(form)

    def set_form(self, form: str) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        form = (form or "").upper()[:5]
        if not form:
            label = QLabel("—")
            label.setObjectName("small")
            self._layout.addWidget(label)
            return
        colors = {
            "V": (ACCENT, "rgba(40,209,124,0.18)"),
            "W": (ACCENT, "rgba(40,209,124,0.18)"),
            "N": (AMBER, "rgba(244,183,64,0.18)"),
            "D": (MUTED, "rgba(130,149,176,0.16)"),
            "L": (RED, "rgba(242,99,114,0.18)"),
        }
        for letter in form:
            color, background = colors.get(letter, (MUTED, "rgba(130,149,176,0.16)"))
            label = QLabel(letter)
            label.setFixedSize(18, 18)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(
                f"color: {color}; background: {background}; border-radius: 5px; "
                f"font-size: 7.5pt; font-weight: 700;"
            )
            self._layout.addWidget(label)


class ProbabilityBar(QWidget):
    def __init__(
        self,
        label: str,
        value: float = 0.0,
        color: str = ACCENT,
        show_value: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.label = QLabel(label)
        self.label.setStyleSheet(f"color: {TEXT_SOFT};")
        self.label.setMinimumWidth(120)
        layout.addWidget(self.label)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(7)
        self.bar.setStyleSheet(
            f"QProgressBar {{ background: {BG_DEEP}; border: none; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
        )
        layout.addWidget(self.bar, 1)
        self.value_label = QLabel("—")
        self.value_label.setStyleSheet(
            f"color: {TEXT}; font-family: 'Cascadia Mono', Consolas, monospace; "
            f"font-size: 9pt; font-weight: 600;"
        )
        self.value_label.setMinimumWidth(48)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if show_value:
            layout.addWidget(self.value_label)
        self.set_value(value)

    def set_value(self, value: float) -> None:
        value = max(0.0, min(1.0, float(value or 0.0)))
        self.bar.setValue(int(round(value * 1000)))
        self.value_label.setText(f"{value * 100:.1f} %")


class Banner(QFrame):
    KINDS = {
        "info": (BLUE, "rgba(76,141,255,0.08)", "i"),
        "warning": (AMBER, "rgba(244,183,64,0.08)", "!"),
        "error": (RED, "rgba(242,99,114,0.08)", "!"),
        "success": (ACCENT, "rgba(40,209,124,0.08)", "✓"),
    }

    def __init__(self, text: str = "", kind: str = "info", parent=None):
        super().__init__(parent)
        self.setVisible(False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(9)
        self.icon = QLabel("i")
        self.icon.setFixedSize(18, 18)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        layout.addWidget(self.label, 1)
        self.set_message(text, kind)

    def set_message(self, text: str, kind: str = "info") -> None:
        if not text:
            self.setVisible(False)
            return
        color, background, symbol = self.KINDS.get(kind, self.KINDS["info"])
        self.setStyleSheet(
            f"QFrame {{ background: {background}; border: 1px solid {color}40; "
            f"border-radius: 9px; }}"
        )
        self.icon.setText(symbol)
        self.icon.setStyleSheet(
            f"color: {color}; font-weight: 700; border: 1px solid {color}; "
            f"border-radius: 9px; font-size: 8pt;"
        )
        self.label.setText(text)
        self.label.setStyleSheet(f"color: {TEXT_SOFT};")
        self.setVisible(True)


class EmptyState(QWidget):
    def __init__(
        self,
        title: str,
        text: str = "",
        action_text: str | None = None,
        symbol: str = "◌",
        parent=None,
    ):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 26, 20, 26)
        layout.setSpacing(8)
        icon = QLabel(symbol)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(f"color: {MUTED}; font-size: 28pt;")
        layout.addWidget(icon)
        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet(f"color: {TEXT}; font-size: 11pt; font-weight: 600;")
        layout.addWidget(title_label)
        if text:
            text_label = QLabel(text)
            text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            text_label.setWordWrap(True)
            text_label.setStyleSheet(f"color: {MUTED};")
            layout.addWidget(text_label)
        self.button: QPushButton | None = None
        if action_text:
            self.button = QPushButton(action_text)
            self.button.setObjectName("primary")
            self.button.setFixedWidth(180)
            row = QHBoxLayout()
            row.addStretch()
            row.addWidget(self.button)
            row.addStretch()
            layout.addLayout(row)


class InfoRow(QWidget):
    """Paire libelle / valeur compacte."""

    def __init__(self, label: str, value: str = "—", mono: bool = False, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.label = QLabel(label)
        self.label.setStyleSheet(f"color: {MUTED};")
        layout.addWidget(self.label)
        layout.addStretch()
        self.value = QLabel(value)
        style = f"color: {TEXT_SOFT}; font-weight: 600;"
        if mono:
            style += " font-family: 'Cascadia Mono', Consolas, monospace;"
        self.value.setStyleSheet(style)
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.value)

    def set_value(self, value: str) -> None:
        self.value.setText(value)


class Divider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("divider")
        self.setFixedHeight(1)


class SmallButton(QPushButton):
    def __init__(self, text: str, primary: bool = False, parent=None):
        super().__init__(text, parent)
        if primary:
            self.setObjectName("primary")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("padding: 4px 9px; font-size: 8.5pt;")


def make_mono_label(text: str, size: float = 9.5, color: str = TEXT, bold: bool = False) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        f"color: {color}; font-family: 'Cascadia Mono', Consolas, monospace; "
        f"font-size: {size}pt; {'font-weight: 700;' if bold else ''}"
    )
    return label


def table_item(text: str, align_right: bool = False, color: str | None = None, bold: bool = False):
    from PyQt6.QtWidgets import QTableWidgetItem

    item = QTableWidgetItem(str(text))
    if align_right:
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if color:
        item.setForeground(QColor(color))
    if bold:
        font = item.font()
        font.setBold(True)
        item.setFont(font)
    return item
