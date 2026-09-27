"""Design tokens for the orb, as a QML-free Python source of truth.

Values come from docs/ui/tokens.md. Keeping them here as well means the Python
side (state mapping, window behavior) and the QML side cannot drift: the app
exposes them to QML as context properties.
"""

# Dark ambient palette. Hue carries state; the rest is the surround.
COLOR_BACKGROUND = "#0B0E14"
COLOR_BACKGROUND_SOFT = "#121722"
COLOR_TEXT = "#E6E9F0"
COLOR_TEXT_DIM = "#8B93A7"
COLOR_ACCENT = "#4DA3FF"
COLOR_BORDER = "#1E2533"

# Per-state core colors. Each state also has a distinct FORM, so the orb remains
# readable in grayscale (docs/ui/orb-states.md).
STATE_COLORS = {
    "idle": "#4DA3FF",           # calm blue, slow breathing
    "listening": "#38D39F",      # green, ring expands
    "transcribing": "#F2C14E",   # amber, dashes rotate
    "thinking": "#B07CFF",       # violet, orbit accelerates
    "speaking": "#FF7AC6",       # pink, strong pulse
    "error": "#FF5C5C",          # red, sharp jitter then hold
    "muted": "#5A6274",          # grey, hollow ring
    "connecting": "#3F4859",     # darker grey than muted: distinct hue value
    "backend_down": "#FF8A3D",   # orange, distinct from error red
}

# Motion durations (ms) and easing, from the design tokens.
DURATION_STATE_MS = 320
DURATION_BREATH_MS = 4200
DURATION_PULSE_MS = 120

# Idle render cap: an always-on window must stay cheap.
FPS_ACTIVE = 60
FPS_IDLE = 30
FPS_HIDDEN = 0

# Geometry
ORB_COMPACT_SIZE = 180
ORB_EXPANDED_SIZE = 260
WINDOW_COMPACT = (220, 220)
WINDOW_EXPANDED = (520, 420)

# Audio reactivity (docs/ui/audio-reactivity.md)
LEVEL_GATE = 0.02        # below this, treat as silence
LEVEL_GAIN = 2.2
LEVEL_GAMMA = 0.7
ATTACK = 0.55
DECAY = 0.08


def state_color(state: str) -> str:
    return STATE_COLORS.get(state, COLOR_ACCENT)
