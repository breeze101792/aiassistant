"""Design tokens for the TUI orb, from docs/ui/tui/tokens.md.

Every glyph, attribute, color pair, and spacing value the renderer uses lives
here, so no component hard-codes a value. The GUI orb keeps its tokens in
``orb/theme.py``; this is the terminal counterpart.
"""

# ── Layout arithmetic ────────────────────────────────────────
PROGRAM_NAME = "aiassistant.tui"

# Fixed chrome: header, rule, meter, rule, composer, status.
CHROME_ROWS = 6
TRANSCRIPT_TOP = 2

# Minimum usable terminal (layout.md § Too small).
MIN_COLS = 60
MIN_ROWS = 16

# Transcript row anatomy (tokens.md § Row layout arithmetic).
COL_GUTTER = 10
COL_TIME = 8

# Level meter.
COL_METER_SOURCE = 4
COL_METER_BAR_BASELINE = 20
COL_METER_BAR_WIDE = 30
WIDE_COLS = 120

# Composer.
COMPOSER_PROMPT = "you> "
COMPOSER_PROMPT_COLS = 5
COMPOSER_PLACEHOLDER = "Type a message..."
OVERFLOW_MARKER = "<"
# Dim marker when the composer holds a multi-line paste; ``{n}`` is the extra
# line count (layout.md § Composer).
MULTILINE_MARKER = " (+{n} lines)"

# Redraw tick. One erase + full repaint at 10 Hz (layout.md § Resize).
DRAW_INTERVAL_S = 0.1
INPUT_BATCH = 32

# getch() waits this long for the rest of an escape sequence before assuming a
# bare Esc. Small enough not to stall the loop, long enough for arrow keys.
INPUT_TIMEOUT_MS = 25

# Sentinels for "scrolled to the very top" and "pinned to the newest".
SCROLL_MAX = 10 ** 9

# The bridge reports this state when the socket is up.
BRIDGE_CONNECTED = "connected"

# ── Identity and badge defaults ──────────────────────────────
DEFAULT_IDENTITY = "Jarvis"
DEFAULT_HARNESS = "native"
UNKNOWN_MODEL = "unknown"
BACKEND_DOWN_TEXT = "! Backend down"

# Ambient sub-cues shown under the transcript while a state is active, from the
# captured mockup (mockup.txt). Drawn dim at ``AMBIENT_COL``, no gutter.
AMBIENT_COL = 2
AMBIENT_CUES = {
    "listening": ".. hearing you ..",
    "transcribing": ".. converting speech to text ..",
    "muted": "(capture stopped; the orb shows Muted)",
    "backend_down": "(harness unhealthy: backend-down overlay on a base state)",
}
BRIDGE_DOWN_LINE = "(bridge unreachable, retrying)"
BRIDGE_RETRY_LINE = "retrying: {state}"

# ── State words and forms (states.md § The state table) ──────
STATE_LABELS = {
    "connecting": "Connecting...",
    "idle": "Idle",
    "muted": "Muted",
    "listening": "Listening",
    "transcribing": "Transcribing",
    "thinking": "Thinking",
    "speaking": "Speaking",
    "error": "Error",
}

ASCII_GLYPHS = {
    "connecting": ":o:",
    "idle": "(o)",
    "muted": "/o/",
    "listening": ">o<",
    "transcribing": "}o{",
    "thinking": "~o~",
    "speaking": "<o>",
    "error": "%o%",
}

# Defined in tokens.md but not selected by default: the task and the mockup are
# ASCII-first, and a fixed glyph keeps captures stable. See select_glyphs().
UNICODE_GLYPHS = {
    "connecting": "\u2218o\u2218",
    "idle": "(\u25cb)",
    "muted": "\u2298o\u2298",
    "listening": "\u227bo\u227a",
    "transcribing": "\u27ebo\u27ea",
    "thinking": "\u2248o\u2248",
    "speaking": "\u227ao\u227b",
    "error": "\u00a4o\u00a4",
}

STREAMING_CURSOR = "_"
METER_FILL = "#"
METER_EMPTY = "-"
RULE_CHAR = "-"
SCROLL_UP = "^"
SCROLL_DOWN = "v"
PINNED_TEXT = "pinned"

# ── Color pairs (tokens.md § Color pairs) ────────────────────
CP_STATE = 1
CP_DIM = 2
CP_ERROR = 3
CP_WARN = 4
CP_ACCENT = 5
CP_USER = 6

# Per-state foreground, ANSI indices. The 256-color value preserves the GUI's
# luminance ordering; the 8-color value is the terminal's own palette.
STATE_COLOR_8 = {
    "connecting": 4,
    "muted": 7,
    "idle": 6,
    "thinking": 5,
    "error": 1,
    "transcribing": 6,
    "listening": 2,
    "speaking": 3,
}
STATE_COLOR_256 = {
    "connecting": 24,
    "muted": 245,
    "idle": 67,
    "thinking": 141,
    "error": 203,
    "transcribing": 75,
    "listening": 79,
    "speaking": 221,
}
# Light grey for the dim/secondary pair. Never bright-black (index 8): on a
# dark or transparent theme that is the background, so dim text vanishes.
FG_DIM_256 = 250
FG_ERROR = 1
FG_WARN = 3
FG_ACCENT = 6
FG_USER = 2


def dim_fg(colors: int) -> int:
    """Foreground for the dim/secondary pair.

    The 256-color value is a light grey, never the bright-black index 8: on a
    dark theme a terminal maps 8 to near-black, which disappears against the
    background. An 8-color terminal has no grey, so it uses the terminal's own
    white, which ``A_DIM`` renders as grey.
    """
    return FG_DIM_256 if colors >= 256 else 7

# ── Terminal key codes ───────────────────────────────────────
CTRL_C = 3
CTRL_D = 4
CTRL_L = 12
CTRL_T = 20
CTRL_DOT = 30
ESCAPE = 27
BACKSPACE = 127
DELETE = 8


def state_fg(state: str, colors: int) -> int:
    """Foreground index for a state, honoring the terminal's color depth."""
    table = STATE_COLOR_256 if colors >= 256 else STATE_COLOR_8
    return table.get(state, table["idle"])


def select_glyphs() -> dict:
    """The active form glyphs.

    ASCII is the baseline and the default. The Unicode upgrade in tokens.md is
    opt-in only: the project is ASCII-first and the captured mockup uses ASCII.
    """
    return ASCII_GLYPHS


def state_label(state: str) -> str:
    return STATE_LABELS.get(state, state.replace("_", " ").title())
