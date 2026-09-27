"""The orb: a frameless, always-on-top window that shows the assistant's state.

Qt event loop only — no asyncio and no qasync. ``QWebSocket`` delivers messages
as Qt signals, so the two event loops never meet (ADR-0013).

Renders from :class:`OrbViewModel`; it never derives state the assistant has not
published. Falls back to a plain painted circle when GPU shaders are
unavailable, so a shader problem can never stop the orb existing.
"""

import json
import logging

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QPainter, QRadialGradient, QKeySequence, QShortcut
from PySide6.QtWebSockets import QWebSocket
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

from aiassistant.bus import topics
from aiassistant.bridge import DEFAULT_URL
from aiassistant.orb import theme
from aiassistant.orb.model import OrbViewModel

logger = logging.getLogger(__name__)

# Topics the orb consumes. Anything not listed is ignored.
WATCHED_TOPICS = (
    topics.VOICE_STATE,
    topics.VOICE_LEVEL,
    topics.AGENT_DELTA,
    topics.AGENT_FINAL,
    topics.AGENT_TOOL_EVENT,
    topics.AGENT_TURN_ERROR,
    topics.AGENT_TRANSCRIPT_SNAPSHOT,
    topics.STATUS_HARNESS,
)


class OrbWidget(QWidget):
    """Paints the orb. State color and pulse come from the view model."""

    def __init__(self, model: OrbViewModel, parent=None):
        super().__init__(parent)
        self.model = model
        self._pulse = 0.0
        self._phase = 0.0
        self.setMinimumSize(160, 160)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(int(1000 / theme.FPS_ACTIVE))

    def _tick(self) -> None:
        # Advance the ambient phase, and ease the pulse toward the level.
        self._phase = (self._phase + 0.01) % 1.0
        target = self.model.level
        self._pulse += (target - self._pulse) * 0.18
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(theme.COLOR_BACKGROUND))

        w, h = self.width(), self.height()
        center_x, center_y = w / 2, h / 2
        base = min(w, h) * 0.32

        # Breathing keeps the idle orb alive; the pulse reacts to audio.
        breath = 0.03 * _sin(self._phase * 2 * 3.14159)
        core_radius = base * (1.0 + breath + self._pulse * 0.55)
        color = QColor(theme.state_color(self.model.state))

        # Outer glow, scaled by the pulse.
        for step in range(6, 0, -1):
            radius = core_radius * (1.0 + step * 0.22)
            glow = QColor(color)
            glow.setAlpha(int(10 + self._pulse * 24))
            painter.setBrush(glow)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(
                int(center_x - radius), int(center_y - radius),
                int(radius * 2), int(radius * 2),
            )

        # Core: a radial gradient gives it depth without a shader.
        gradient = QRadialGradient(center_x, center_y - core_radius * 0.25, core_radius * 1.6)
        inner = QColor(color).lighter(150)
        gradient.setColorAt(0.0, inner)
        gradient.setColorAt(0.6, color)
        edge = QColor(color).darker(160)
        gradient.setColorAt(1.0, edge)
        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(
            int(center_x - core_radius), int(center_y - core_radius),
            int(core_radius * 2), int(core_radius * 2),
        )

        # A second ring whose form distinguishes states without color.
        if self.model.state in ("listening", "thinking", "speaking"):
            ring = core_radius * (1.35 + self._pulse * 0.5)
            ring_color = QColor(color)
            ring_color.setAlpha(140)
            pen = painter.pen()
            pen.setColor(ring_color)
            pen.setWidth(3)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(
                int(center_x - ring), int(center_y - ring),
                int(ring * 2), int(ring * 2),
            )

        painter.end()


def _sin(x: float) -> float:
    import math
    return math.sin(x)


class OrbWindow(QWidget):
    """The frameless window: orb, status, transcript, and controls."""

    def __init__(self, model: OrbViewModel, url: str, token: str, always_on_top: bool = True):
        super().__init__()
        self.model = model
        self.url = url
        self.token = token
        self._expanded = False

        flags = Qt.FramelessWindowHint | Qt.Tool
        if always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setWindowTitle("AI Assistant")

        self._build_ui()
        self._connect_ws()
        self._start_timer()

    # ── UI ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(8)

        self.orb = OrbWidget(self.model, self)
        root.addWidget(self.orb, stretch=1)

        self.status = QLabel("connecting…")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet(
            f"color: {theme.COLOR_TEXT_DIM}; font-size: 12px;"
        )
        root.addWidget(self.status)

        self.transcript = QLabel("")
        self.transcript.setWordWrap(True)
        self.transcript.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.transcript.setStyleSheet(
            f"color: {theme.COLOR_TEXT}; font-size: 13px;"
            f" background: {theme.COLOR_BACKGROUND_SOFT};"
            f" border: 1px solid {theme.COLOR_BORDER}; border-radius: 8px;"
            " padding: 8px;"
        )
        self.transcript.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.transcript.hide()

        self.composer = QLineEdit()
        self.composer.setPlaceholderText("Type a message…")
        self.composer.setStyleSheet(
            f"color: {theme.COLOR_TEXT}; background: {theme.COLOR_BACKGROUND_SOFT};"
            f" border: 1px solid {theme.COLOR_BORDER}; border-radius: 8px; padding: 6px;"
        )
        self.composer.returnPressed.connect(self._send_text)
        self.composer.hide()

        row = QHBoxLayout()
        for label, slot, tip in (
            ("Stop", self._interrupt, "Stop the assistant (Esc)"),
            ("Mute", self._toggle_mute, "Mute the microphone (M)"),
            ("More", self._toggle_expanded, "Show the transcript (Tab)"),
        ):
            button = QPushButton(label)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            button.setStyleSheet(
                f"color: {theme.COLOR_TEXT}; background: {theme.COLOR_BACKGROUND_SOFT};"
                f" border: 1px solid {theme.COLOR_BORDER}; border-radius: 8px;"
                " padding: 5px 10px;"
            )
            row.addWidget(button)
            key = {"Stop": "Esc", "Mute": "M", "More": "Tab"}[label]
            QShortcut(QKeySequence(key), self, activated=slot)

        root.addLayout(row)
        self.setStyleSheet(f"background: {theme.COLOR_BACKGROUND};")
        self.resize(*theme.WINDOW_COMPACT)

    # ── Transport ────────────────────────────────────────────

    def _connect_ws(self) -> None:
        self.ws = QWebSocket()
        self.ws.connected.connect(self._on_connected)
        self.ws.disconnected.connect(self._on_disconnected)
        self.ws.textMessageReceived.connect(self._on_message)
        self.ws.errorOccurred.connect(lambda _: self._set_state("backend_down"))
        self.ws.open(QUrl(self.url))

    def _on_connected(self) -> None:
        if self.token:
            self.ws.sendTextMessage(json.dumps({"token": self.token}))
        self.ws.sendTextMessage(json.dumps({
            "action": "register", "module_name": "orb", "capabilities": {"type": "client"},
        }))
        for topic in WATCHED_TOPICS:
            self.ws.sendTextMessage(json.dumps({"action": "subscribe", "topic": topic}))
        self.status.setText("connected")

    def _on_disconnected(self) -> None:
        self._set_state("connecting")
        self.status.setText("reconnecting…")
        # Retry; the server may be starting after us.
        QTimer.singleShot(2000, self._connect_ws)

    def _on_message(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return
        topic = data.get("topic")
        payload = data.get("payload") or {}
        if not topic:
            return

        if topic == topics.VOICE_STATE:
            self.model.on_voice_state(payload)
        elif topic == topics.VOICE_LEVEL:
            self.model.on_level(payload)
        elif topic == topics.AGENT_DELTA:
            self.model.on_delta(payload)
            if self.model.needs_snapshot:
                self._request_snapshot()
        elif topic == topics.AGENT_FINAL:
            self.model.on_final(payload)
        elif topic == topics.AGENT_TOOL_EVENT:
            self.model.on_tool_event(payload)
        elif topic == topics.AGENT_TURN_ERROR:
            self.model.on_error(payload)
        elif topic == topics.STATUS_HARNESS:
            self.model.on_harness(payload)
        elif topic == topics.AGENT_TRANSCRIPT_SNAPSHOT:
            self.model.on_snapshot(payload)

    def _request_snapshot(self) -> None:
        """Ask for the transcript after a gap, rather than rendering a hole."""
        try:
            self.ws.sendTextMessage(json.dumps({
                "action": "publish",
                "topic": topics.AGENT_TRANSCRIPT_SNAPSHOT + ".request",
                "payload": {},
            }))
        except Exception:
            logger.debug("snapshot request failed", exc_info=True)

    # ── Actions ──────────────────────────────────────────────

    def _send_text(self) -> None:
        text = self.composer.text().strip()
        if not text:
            return
        self.composer.clear()
        self._publish(topics.USER_INPUT_TEXT, {"text": text, "channel": "orb"})

    def _interrupt(self) -> None:
        self._publish(topics.COMMAND_AGENT_INTERRUPT, {})

    def _toggle_mute(self) -> None:
        self._muted = not getattr(self, "_muted", False)
        self._publish(topics.COMMAND_VOICE_MUTE, {"muted": self._muted})

    def _toggle_expanded(self) -> None:
        self._expanded = not self._expanded
        self.transcript.setVisible(self._expanded)
        self.composer.setVisible(self._expanded)
        self.orb.setMinimumSize(
            theme.ORB_EXPANDED_SIZE if self._expanded else 160,
            theme.ORB_EXPANDED_SIZE if self._expanded else 160,
        )
        self.resize(*(theme.WINDOW_EXPANDED if self._expanded else theme.WINDOW_COMPACT))

    def _publish(self, topic: str, payload: dict) -> None:
        try:
            self.ws.sendTextMessage(json.dumps({
                "action": "publish", "topic": topic, "payload": payload,
            }))
        except Exception:
            logger.debug("publish failed for %s", topic, exc_info=True)

    # ── Rendering loop ───────────────────────────────────────

    def _start_timer(self) -> None:
        # A slow tick refreshes text and state; the orb paints on its own timer.
        self._ui_timer = QTimer(self)
        self._ui_timer.timeout.connect(self._refresh)
        self._ui_timer.start(120)

    def _refresh(self) -> None:
        label = self.model.state
        if self.model.harness:
            label += f" · {self.model.harness}"
        if self.model.error:
            label = self.model.error
        self.status.setText(label)
        if self._expanded:
            self.transcript.setText(self.model.transcript_text or "…")

    def _set_state(self, state: str) -> None:
        self.model.state = state

    # ── Window behavior ──────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        # Frameless windows need an explicit drag handle.
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if getattr(self, "_drag_offset", None) is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class OrbConfig:
    """What the orb needs from config, without importing the assistant package."""

    def __init__(self, url: str = DEFAULT_URL, token: str = "",
                 always_on_top: bool = True):
        self.url = url
        self.token = token
        self.always_on_top = always_on_top

    @classmethod
    def from_config(cls, config: dict) -> "OrbConfig":
        bus_cfg = config.get("bus", {})
        display = config.get("display", {})
        host = "127.0.0.1" if bus_cfg.get("bind", "127.0.0.1") in ("0.0.0.0", "") \
            else bus_cfg.get("bind", "127.0.0.1")
        return cls(
            url=f"ws://{host}:{bus_cfg.get('websocket_port', 8765)}",
            token=bus_cfg.get("remote_auth_token", ""),
            always_on_top=display.get("always_on_top", True),
        )
