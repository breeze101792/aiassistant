"""Curses rendering for the TUI orb.

Turns an :class:`OrbViewModel` plus a small :class:`UIState` into a full-screen
repaint. Rendering only: it never touches the bus and never imports Qt. The
layout, glyphs, and attributes are those of docs/ui/tui/{tokens,states,layout}.md.

Every draw is one ``erase()`` and a full repaint; partial redraws are not
attempted, so a resize can never desync the screen (layout.md § Resize).
"""

import curses
import logging
import os
import time
from dataclasses import dataclass

from . import tokens

logger = logging.getLogger(__name__)

# Attributes from tokens.md § Attribute set. A_BOLD is "emphasis"; A_DIM is
# "secondary"; A_REVERSE is the one functional cue (cursor and focus).
ATTR_PRIMARY = curses.A_NORMAL
ATTR_SECONDARY = curses.A_DIM
ATTR_EMPHASIS = curses.A_BOLD
ATTR_STREAM = curses.A_REVERSE
ATTR_FOCUS = curses.A_REVERSE


@dataclass
class UIState:
    """Input and chrome state the view model does not own.

    ``overlay`` is the app's reading of the two overlay rules in states.md: a
    harness-class turn error sets ``backend_down``; any other turn error sets
    ``transcript_error``. The base state is kept in ``base_state`` so an overlay
    layers on it instead of replacing it.
    """

    composer: str = ""
    cursor: int = 0
    help_open: bool = False
    scroll: int = 0            # display lines up from the newest; 0 == pinned
    new_count: int = 0         # rows that arrived while unpinned
    base_state: str = "connecting"
    overlay: str = ""          # "" | "backend_down" | "transcript_error"
    error_class: str = ""
    error_dismissed: bool = False
    bridge_state: str = "connecting"

    def display_state(self, model) -> str:
        """The state word/form to render.

        The base state wins while the model reads ``error`` but the last
        ``voice.state`` was something else: a ``transcript-error`` overlay keeps
        the base glyph and lives in the error row, and the header must not flip
        to ``Error`` (states.md § error versus transcript-error). A real
        ``voice.state: error`` sets ``base_state`` to ``error``, so it renders as
        the ``%o%`` glyph.
        """
        if model.state == "error" and self.base_state and self.base_state != "error":
            return self.base_state
        return model.state


@dataclass
class Row:
    """One display line of the transcript."""

    gutter: str
    body: str
    time: str
    role: str
    dim: bool = False
    emphasis: bool = False
    user: bool = False
    error: bool = False
    cursor: int | None = None  # cell index within ``body`` for the stream cursor

    def body_attr(self) -> int:
        attr = ATTR_PRIMARY
        if self.dim:
            attr |= ATTR_SECONDARY
        if self.emphasis:
            attr |= ATTR_EMPHASIS
        return attr


def wrap_text(text: str, width: int) -> list[str]:
    """Word-wrap ``text`` to ``width`` columns, hard-breaking long words."""
    if width < 1:
        return [text]
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if paragraph == "":
            lines.append("")
            continue
        current = ""
        for word in paragraph.split(" "):
            candidate = word if current == "" else current + " " + word
            if len(candidate) <= width:
                current = candidate
                continue
            if current != "":
                lines.append(current)
            while len(word) > width:
                lines.append(word[:width])
                word = word[width:]
            current = word
        lines.append(current)
    return lines or [""]


def clip(text: str, width: int) -> str:
    """Clip ``text`` to ``width``, marking truncation with a trailing ``~``."""
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width == 1:
        return "~"
    return text[: width - 1] + "~"


def _format_time(ts) -> str:
    if not ts:
        return ""
    try:
        return time.strftime("%H:%M:%S", time.localtime(float(ts)))
    except (ValueError, OSError, TypeError):
        return ""


def error_visible(model, ui: UIState) -> bool:
    """Whether the ``!Error`` row is currently shown.

    An error row is hidden once Esc dismisses it; the underlying message stays
    on the model so a new turn can re-surface it.
    """
    return bool(model.error) and not ui.error_dismissed


def _gutter_for(entry: dict, identity: str) -> str:
    role = entry.get("role", "assistant")
    if role == "user":
        return "You"
    if role == "assistant":
        return identity
    if role == "thinking":
        return "Thinking"
    if role == "tool":
        # The view model stores tool rows as ``<name>…`` without a status field;
        # the gutter reads "tool", matching the captured mockup.
        return "tool"
    if role == "error":
        return "!Error"
    return role.replace("_", " ").title() or identity


def _build_entry_rows(entries: list[dict], identity: str, body_width: int) -> list[Row]:
    rows: list[Row] = []
    for entry in entries:
        role = entry.get("role", "assistant")
        text = str(entry.get("text", ""))
        ts = _format_time(entry.get("ts"))
        streaming = bool(entry.get("streaming"))
        gutter = _gutter_for(entry, identity)
        if role == "tool":
            # The view model stores ``<name>…``; the design wants ``name: status``
            # and no streaming cursor on tool rows (layout.md § Roles).
            name = text[:-1] if text.endswith("\u2026") else text
            status = "running" if streaming else "ok"
            text = f"{name}: {status}"
            streaming = False
        wrapped = wrap_text(text, body_width)
        for i, line in enumerate(wrapped):
            is_first = i == 0
            rows.append(Row(
                gutter=gutter if is_first else "",
                body=line,
                time=ts if is_first else "",
                role=role,
                dim=role in ("thinking", "tool"),
                emphasis=False,
                user=role == "user",
                # The stream cursor rides the last line of a live row.
                cursor=len(line) if streaming and i == len(wrapped) - 1 else None,
            ))
    return rows


class Renderer:
    """Draws the whole screen from the view model on demand."""

    def __init__(self, identity: str = tokens.DEFAULT_IDENTITY, glyphs: dict | None = None,
                 hotwords: list[str] | None = None):
        self.identity = identity or tokens.DEFAULT_IDENTITY
        self.glyphs = glyphs or tokens.select_glyphs()
        self.hotwords = [str(h) for h in (hotwords or []) if str(h).strip()]
        self._colors = False
        self._bg = -1
        self._state_color: tuple[str, int] | None = None

    # ── Setup ────────────────────────────────────────────────

    def setup(self) -> None:
        """Register color pairs when the terminal supports them."""
        self._colors = False
        self._state_color = None
        if os.environ.get("NO_COLOR"):
            return
        try:
            if not curses.has_colors():
                return
            curses.start_color()
            try:
                curses.use_default_colors()
                self._bg = -1
            except curses.error:
                self._bg = curses.COLOR_BLACK
            self._init_fixed_pairs()
            self._colors = True
        except curses.error:
            logger.debug("color init failed; continuing monochrome", exc_info=True)
            self._colors = False

    def _init_fixed_pairs(self) -> None:
        colors = curses.tigetnum("colors") or 8
        curses.init_pair(tokens.CP_DIM, tokens.dim_fg(colors), self._bg)
        curses.init_pair(tokens.CP_ERROR, tokens.FG_ERROR, self._bg)
        curses.init_pair(tokens.CP_WARN, tokens.FG_WARN, self._bg)
        curses.init_pair(tokens.CP_ACCENT, tokens.FG_ACCENT, self._bg)
        curses.init_pair(tokens.CP_USER, tokens.FG_USER, self._bg)
        # CP_STATE is re-registered per state; seed it so the pair exists from
        # startup, as the design's construction order requires.
        curses.init_pair(tokens.CP_STATE, tokens.state_fg("idle", colors), self._bg)

    def _pair(self, cp: int, *attrs: int) -> int:
        attr = curses.A_NORMAL
        for extra in attrs:
            attr |= extra
        if self._colors:
            attr |= curses.color_pair(cp)
        return attr

    def _state_pair(self, state: str) -> int:
        if self._colors:
            colors = curses.tigetnum("colors") or 8
            key = (state, colors)
            if key != self._state_color:
                try:
                    curses.init_pair(tokens.CP_STATE, tokens.state_fg(state, colors),
                                     self._bg)
                    self._state_color = key
                except curses.error:
                    logger.debug("state pair init failed", exc_info=True)
        return self._pair(tokens.CP_STATE)

    def _safe(self, win, row: int, col: int, text: str, attr: int = 0) -> None:
        """Draw clipped text, swallowing the bottom-right-corner curses error."""
        if not text:
            return
        try:
            win.addnstr(row, col, text, max(0, len(text)), attr)
        except curses.error:
            pass
        except (UnicodeEncodeError, ValueError):
            logger.debug("dropping text the terminal cannot encode")

    # ── Entry point ──────────────────────────────────────────

    def draw(self, win, model, ui: UIState) -> None:
        """Repaint the whole screen. Never raises out to the caller."""
        try:
            rows, cols = win.getmaxyx()
            win.erase()
            if cols < tokens.MIN_COLS or rows < tokens.MIN_ROWS:
                self._draw_too_small(win, rows, cols)
            else:
                self._draw_full(win, model, ui, rows, cols)
            win.refresh()
        except curses.error:
            logger.debug("curses draw failed", exc_info=True)
        except Exception:
            logger.exception("unexpected render error")

    # ── Too small ────────────────────────────────────────────

    def _draw_too_small(self, win, rows: int, cols: int) -> None:
        lines = (
            f"Terminal too small: need {tokens.MIN_COLS}x{tokens.MIN_ROWS}, "
            f"have {cols}x{rows}.",
            "Resize the window, or press Ctrl+D to quit.",
        )
        top = max(0, (rows - len(lines)) // 2)
        for i, line in enumerate(lines):
            col = max(0, (cols - len(line)) // 2)
            self._safe(win, top + i, col, line, ATTR_EMPHASIS)

    # ── Full layout ──────────────────────────────────────────

    def _draw_full(self, win, model, ui: UIState, rows: int, cols: int) -> None:
        row_status = rows - 1
        row_composer = rows - 2
        row_rule_low = rows - 3
        row_meter = rows - 4
        transcript_top = tokens.TRANSCRIPT_TOP
        transcript_bottom = rows - 5
        transcript_height = max(0, transcript_bottom - transcript_top + 1)

        self._draw_header(win, model, ui, cols)
        self._draw_rule(win, 1, cols)
        self._draw_transcript(win, model, ui, transcript_top, transcript_bottom,
                              transcript_height, cols)
        self._draw_meter(win, model, ui, row_meter, cols)
        self._draw_rule(win, row_rule_low, cols)
        self._draw_composer(win, ui, row_composer, cols)
        self._draw_status(win, model, ui, row_status, cols)
        if ui.help_open:
            self._draw_help(win, rows, cols)

    def _draw_rule(self, win, row: int, cols: int) -> None:
        self._safe(win, row, 0, tokens.RULE_CHAR * cols, ATTR_SECONDARY)

    def _draw_header(self, win, model, ui: UIState, cols: int) -> None:
        state = ui.display_state(model)
        glyph = self.glyphs.get(state, self.glyphs["idle"])
        label = tokens.state_label(state)
        label_attr = self._state_pair(state)
        if state == "muted":
            label_attr |= ATTR_SECONDARY

        badge = (f"{model.harness or tokens.DEFAULT_HARNESS} / "
                 f"{model.model or tokens.UNKNOWN_MODEL}")
        backend_down = ui.overlay == "backend_down"
        if backend_down:
            badge += " !"
        badge_attr = self._pair(tokens.CP_WARN, ATTR_EMPHASIS) if backend_down \
            else ATTR_EMPHASIS
        badge_col = max(0, cols - len(badge))

        self._safe(win, 0, 0, glyph + " ", label_attr)
        label_col = len(glyph) + 1
        avail = max(0, badge_col - label_col - 1)
        self._safe(win, 0, label_col, clip(label, avail), label_attr)
        if backend_down:
            overlay_col = label_col + min(len(label), avail)
            overlay_avail = max(0, badge_col - overlay_col - 1)
            self._safe(win, 0, overlay_col,
                       clip("  " + tokens.BACKEND_DOWN_TEXT, overlay_avail),
                       self._pair(tokens.CP_WARN, ATTR_EMPHASIS))
        self._safe(win, 0, badge_col, badge, badge_attr)

    def _collect_rows(self, model, ui: UIState, body_width: int) -> list[Row]:
        rows: list[Row] = []
        if ui.bridge_state != tokens.BRIDGE_CONNECTED:
            rows.append(Row(gutter="", body=" " * tokens.AMBIENT_COL
                            + tokens.BRIDGE_DOWN_LINE,
                            time="", role="status", dim=True))
            rows.append(Row(gutter="", body=" " * tokens.AMBIENT_COL
                            + tokens.BRIDGE_RETRY_LINE.format(state=ui.bridge_state),
                            time="", role="status", dim=True))
        rows.extend(_build_entry_rows(model.transcript, self.identity, body_width))
        cue_key = "backend_down" if ui.overlay == "backend_down" \
            else ui.display_state(model)
        cue = tokens.AMBIENT_CUES.get(cue_key)
        if cue:
            rows.append(Row(gutter="", body=" " * tokens.AMBIENT_COL + cue,
                            time="", role="status", dim=True))
        if error_visible(model, ui):
            chip = f"[{ui.error_class}] " if ui.error_class else ""
            rows.append(Row(gutter="!Error", body=chip + model.error, time="",
                            role="error", emphasis=True))
            if model.hint:
                rows.append(Row(gutter="", body=f"hint: {model.hint}", time="",
                                role="hint", dim=True))
        return rows

    def _draw_transcript(self, win, model, ui: UIState, top: int, bottom: int,
                         height: int, cols: int) -> None:
        if height <= 0:
            return
        body_width = max(1, cols - tokens.COL_GUTTER - 1 - tokens.COL_TIME)
        rows = self._collect_rows(model, ui, body_width)
        if not rows:
            self._draw_empty(win, top, height, cols)
            return

        offset = min(ui.scroll, max(0, len(rows) - height))
        start = max(0, len(rows) - height - offset)
        visible = rows[start:start + height]

        for i, row in enumerate(visible):
            self._draw_row(win, top + i, row, cols)

        self._draw_scroll_indicators(win, rows, start, visible, top, bottom, cols)

    def _draw_row(self, win, row: int, entry: Row, cols: int) -> None:
        if entry.role == "status":
            # Ambient cues (and the bridge lines) are full-width, not transcript
            # rows: they start at column 0 with no gutter or time.
            self._safe(win, row, 0, entry.body[:cols],
                       self._pair(tokens.CP_DIM, ATTR_SECONDARY))
            return

        gutter = entry.gutter[: tokens.COL_GUTTER - 1]
        gutter_text = f"{gutter:<{tokens.COL_GUTTER}}"
        if entry.user:
            gutter_attr = self._pair(tokens.CP_USER, ATTR_SECONDARY)
        else:
            gutter_attr = self._pair(tokens.CP_DIM, ATTR_SECONDARY)
        self._safe(win, row, 0, gutter_text, gutter_attr)

        body_width = max(1, cols - tokens.COL_GUTTER - 1 - tokens.COL_TIME)
        body = clip(entry.body, body_width)
        body_attr = entry.body_attr()
        if entry.error:
            body_attr |= self._pair(tokens.CP_ERROR)
        self._safe(win, row, tokens.COL_GUTTER, body, body_attr)

        if entry.time:
            self._safe(win, row, max(0, cols - tokens.COL_TIME), entry.time,
                       self._pair(tokens.CP_DIM, ATTR_SECONDARY))

        if entry.cursor is not None:
            pos = tokens.COL_GUTTER + min(entry.cursor, len(body))
            if pos >= cols - tokens.COL_TIME:
                pos = cols - tokens.COL_TIME - 1
            self._safe(win, row, max(0, pos), tokens.STREAMING_CURSOR,
                       self._pair(tokens.CP_ACCENT, ATTR_STREAM))

    def _draw_scroll_indicators(self, win, rows: list[Row], start: int,
                                visible: list[Row], top: int, bottom: int,
                                cols: int) -> None:
        if start > 0:
            self._safe(win, top, max(0, cols - 1), tokens.SCROLL_UP, ATTR_SECONDARY)
        if start + len(visible) < len(rows):
            self._safe(win, bottom, max(0, cols - 1), tokens.SCROLL_DOWN,
                       ATTR_SECONDARY)

    def _draw_empty(self, win, top: int, height: int, cols: int) -> None:
        text = 'No messages yet. Say "hi jarvis" or type below.'
        row = top + max(0, (height - 1) // 2)
        col = max(0, (cols - len(text)) // 2)
        self._safe(win, row, col, text, self._pair(tokens.CP_DIM, ATTR_SECONDARY))

    def _draw_meter(self, win, model, ui: UIState, row: int, cols: int) -> None:
        state = ui.display_state(model)
        if state == "listening":
            live_source = "input"
        elif state == "speaking":
            live_source = "output"
        else:
            live_source = None
        live = live_source is not None and model.level_source == live_source
        level = model.level if live else 0.0

        label = "mic" if model.level_source == "input" else "spk"
        bar_cells = tokens.COL_METER_BAR_WIDE if cols >= tokens.WIDE_COLS \
            else tokens.COL_METER_BAR_BASELINE
        filled = int(round(level * bar_cells))
        filled = max(0, min(bar_cells, filled))
        percent = f"{round(level * 100):>3}%"

        col = 0
        self._safe(win, row, col, label, self._pair(tokens.CP_DIM, ATTR_SECONDARY))
        col += tokens.COL_METER_SOURCE
        self._safe(win, row, col, "[", ATTR_SECONDARY)
        fill_attr = self._pair(tokens.CP_ACCENT, ATTR_STREAM) if self._colors \
            else ATTR_STREAM
        # Draw the fill and the empty tail separately so each gets its own cue.
        self._safe(win, row, col + 1, tokens.METER_FILL * filled, fill_attr)
        self._safe(win, row, col + 1 + filled, tokens.METER_EMPTY * (bar_cells - filled),
                   self._pair(tokens.CP_DIM, ATTR_SECONDARY))
        self._safe(win, row, col + 1 + bar_cells, "]", ATTR_SECONDARY)
        self._safe(win, row, col + bar_cells + 3, percent,
                   self._pair(tokens.CP_DIM, ATTR_SECONDARY))

    def _draw_composer(self, win, ui: UIState, row: int, cols: int) -> None:
        prompt = tokens.COMPOSER_PROMPT
        self._safe(win, row, 0, prompt, self._pair(tokens.CP_ACCENT, ATTR_EMPHASIS))
        field = max(1, cols - tokens.COMPOSER_PROMPT_COLS)
        base = tokens.COMPOSER_PROMPT_COLS

        if not ui.composer:
            # The cursor cell sits at the insertion point, the placeholder just
            # after it: "you> _Type a message..." (layout.md § Composer).
            self._safe(win, row, base, " ", ATTR_FOCUS)
            self._safe(win, row, base + 1, tokens.COMPOSER_PLACEHOLDER,
                       self._pair(tokens.CP_DIM, ATTR_SECONDARY))
            return

        # A multi-line paste keeps the one-row chrome: only the first line is
        # shown, with a dim marker for the lines it hides (layout.md § Composer).
        text = ui.composer
        first_line, _, rest = text.partition("\n")
        extra_lines = rest.count("\n") + 1 if rest else 0
        cursor = min(ui.cursor, len(first_line))
        marker = (tokens.MULTILINE_MARKER.format(n=extra_lines) if extra_lines
                  else "")
        avail = max(1, field - len(marker))
        view, vcur = self._composer_view(first_line, cursor, avail)
        self._safe(win, row, base, view, ATTR_PRIMARY)
        cell = view[vcur] if 0 <= vcur < len(view) else " "
        self._safe(win, row, base + max(0, min(vcur, avail - 1)), cell, ATTR_FOCUS)
        if marker:
            self._safe(win, row, base + len(view), marker,
                       self._pair(tokens.CP_DIM, ATTR_SECONDARY))

    @staticmethod
    def _composer_view(text: str, cursor: int, field: int) -> tuple[str, int]:
        """Return the visible slice and the cursor's column within it.

        When the text overflows, the start is clipped and a ``<`` marker holds
        column 0, so the insertion point and the newest characters stay visible
        (layout.md § Composer).
        """
        if len(text) <= field:
            return text, min(cursor, len(text))
        span = max(1, field - 1)
        start = max(0, cursor - span + 1)
        if cursor < span:
            start = 0
        view = tokens.OVERFLOW_MARKER + text[start:start + span]
        vcur = cursor - start + 1
        return view[:field], min(vcur, field - 1)

    def _draw_status(self, win, model, ui: UIState, row: int, cols: int) -> None:
        if error_visible(model, ui):
            esc = "Esc dismiss"
        elif ui.display_state(model) == "muted":
            esc = "Esc unmute"
        else:
            esc = "Esc stop"
        left = (f"{esc}  ^T mute  ^L clear  ^D quit")
        if cols >= tokens.WIDE_COLS:
            left += "  PgUp/PgDn scroll"
        left += "  F1 help"

        if ui.scroll == 0:
            right = tokens.PINNED_TEXT
        else:
            right = f"{ui.new_count} new"
        right_col = max(0, cols - len(right))
        avail = max(0, right_col - 1)
        self._safe(win, row, 0, clip(left, avail),
                   self._pair(tokens.CP_DIM, ATTR_SECONDARY))
        self._safe(win, row, right_col, right,
                   self._pair(tokens.CP_DIM, ATTR_SECONDARY))

    HELP_LINES = (
        "F1, Esc     close this help",
        "Ctrl+D      quit the TUI (assistant keeps running)",
        "Enter       send the composer",
        "Esc         close help / clear input / interrupt",
        "Ctrl+T      toggle mute",
        "Ctrl+.      interrupt a turn",
        "Ctrl+L      clear the transcript view",
        "PgUp, PgDn  scroll one page",
        "Up, Down    scroll one line",
        "Home, End   oldest / newest",
        "/clear      clear the transcript view",
        "/help       show this help",
    )

    def _help_lines(self) -> tuple[str, ...]:
        """The help overlay, with the configured wake phrase named.

        The phrase comes from config, never hard-coded, so the overlay says what
        the voice pipeline actually listens for.
        """
        line = self._hotword_line()
        return (line,) + self.HELP_LINES if line else self.HELP_LINES

    def _hotword_line(self) -> str:
        if not self.hotwords:
            return ""
        quoted = ", ".join(f'"{p}"' for p in self.hotwords)
        return f"Hotword     say {quoted} to activate audio input"

    def _draw_help(self, win, rows: int, cols: int) -> None:
        lines = self._help_lines()
        width = min(cols, max(len(line) for line in lines) + 4)
        height = min(rows, len(lines) + 2)
        top = max(0, (rows - height) // 2)
        left = max(0, (cols - width) // 2)
        blank = " " * width
        for i in range(height):
            self._safe(win, top + i, left, blank, ATTR_PRIMARY)
        for i, line in enumerate(lines):
            if i + 1 >= height:
                break
            self._safe(win, top + 1 + i, left + 2, clip(line, width - 4),
                       self._pair(tokens.CP_ACCENT, ATTR_PRIMARY))
