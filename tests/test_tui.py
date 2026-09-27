"""TUI orb tests.

The curses screen cannot be opened in a unit test (and must not be). These
tests drive the parts that are pure: key dispatch, the publish side effects,
the overlay rules, and the Qt-free import. A fake bridge records publishes, so
no socket is opened.

Real-terminal behavior (alternate screen, restoration, resize) is on-target and
stated as unverified in PLAN.md.
"""

import asyncio

from aiassistant.bus import topics
from aiassistant.tui.app import TuiApp, WATCHED_TOPICS
from aiassistant.tui import tokens


class FakeBridge:
    """Records publishes and subscriptions without a socket."""

    def __init__(self):
        self.published: list[tuple[str, dict]] = []
        self.subscribed: list[str] = []
        self.closed = False

    @property
    def subscriptions(self) -> set[str]:
        return set(self.subscribed)

    async def subscribe(self, topic):
        self.subscribed.append(topic)

    async def publish(self, topic, payload=None):
        self.published.append((topic, payload or {}))

    async def run(self):
        return None

    async def close(self):
        self.closed = True


def _app(bridge=None):
    return TuiApp(url="ws://127.0.0.1:1", token="", identity="Jarvis",
                  bridge=bridge or FakeBridge())


def _drive(app, action):
    """Run a key action inside a loop and let its publishes settle.

    ``_handle_key`` schedules publishes with ``ensure_future``, so it needs a
    running loop; the app is designed to run inside one.
    """
    async def scenario():
        action()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    asyncio.run(scenario())


class TestWatchSet:
    # The GUI orb's watch set, restated here because importing orb.app needs
    # PySide6, which is not installed in a headless test environment.
    ORB_TOPICS = (
        topics.VOICE_STATE,
        topics.VOICE_LEVEL,
        topics.AGENT_DELTA,
        topics.AGENT_FINAL,
        topics.AGENT_TOOL_EVENT,
        topics.AGENT_TURN_ERROR,
        topics.AGENT_TRANSCRIPT_SNAPSHOT,
        topics.STATUS_HARNESS,
    )

    def test_watches_the_same_topics_as_the_orb(self):
        assert tuple(WATCHED_TOPICS) == self.ORB_TOPICS

    def test_uses_topic_constants_not_literals(self):
        assert topics.VOICE_STATE in WATCHED_TOPICS
        assert topics.AGENT_DELTA in WATCHED_TOPICS


class TestInputPublishes:
    def test_enter_publishes_user_input_on_the_tui_channel(self):
        bridge = FakeBridge()
        app = _app(bridge)

        def action():
            for ch in "hello":
                app._insert(ch)
            app._submit()

        _drive(app, action)
        assert (topics.USER_INPUT_TEXT, {"text": "hello",
                                         "channel": topics.CHANNEL_TUI}) in bridge.published

    def test_slash_command_stays_local(self):
        bridge = FakeBridge()
        app = _app(bridge)

        def action():
            for ch in "/help":
                app._insert(ch)
            app._submit()

        _drive(app, action)
        assert bridge.published == []
        assert app.ui.help_open is True

    def test_ctrl_t_toggles_mute_and_publishes(self):
        bridge = FakeBridge()
        app = _app(bridge)
        _drive(app, lambda: app._handle_key(tokens.CTRL_T))
        assert bridge.published == [(topics.COMMAND_VOICE_MUTE, {"muted": True})]

    def test_ctrl_dot_interrupts(self):
        bridge = FakeBridge()
        app = _app(bridge)
        _drive(app, lambda: app._handle_key(tokens.CTRL_DOT))
        assert bridge.published == [(topics.COMMAND_AGENT_INTERRUPT, {})]

    def test_ctrl_d_stops(self):
        app = _app()
        app._handle_key(tokens.CTRL_D)
        assert app._stop is True

    def test_ctrl_c_does_not_quit(self):
        app = _app()
        app._handle_key(tokens.CTRL_C)
        assert app._stop is False

    def test_printable_inserts(self):
        app = _app()
        app._handle_key(ord("x"))
        assert app.ui.composer == "x"

    def test_empty_submit_publishes_nothing(self):
        bridge = FakeBridge()
        app = _app(bridge)
        _drive(app, app._submit)
        assert bridge.published == []


class TestEscapeOrder:
    def test_esc_closes_help_first(self):
        app = _app()
        app.ui.help_open = True
        app._handle_escape()
        assert app.ui.help_open is False

    def test_esc_clears_the_composer_before_interrupting(self):
        bridge = FakeBridge()
        app = _app(bridge)

        def action():
            app._insert("draft")
            app._handle_escape()

        _drive(app, action)
        assert app.ui.composer == ""
        assert bridge.published == []

    def test_esc_interrupts_an_active_turn(self):
        bridge = FakeBridge()
        app = _app(bridge)
        app.model.state = "thinking"
        _drive(app, app._handle_escape)
        assert bridge.published == [(topics.COMMAND_AGENT_INTERRUPT, {})]

    def test_esc_never_quits(self):
        app = _app()
        app._handle_escape()
        assert app._stop is False


class TestFeedAndOverlays:
    def test_voice_state_updates_the_base_state(self):
        app = _app()
        app._on_message(topics.VOICE_STATE, {"state": "listening"})
        assert app.ui.base_state == "listening"
        assert app.model.state == "listening"

    def test_harness_error_sets_backend_down(self):
        app = _app()
        app._on_message(topics.AGENT_TURN_ERROR,
                        {"message": "down", "class": "harness"})
        assert app.ui.overlay == "backend_down"

    def test_a_delta_clears_backend_down(self):
        app = _app()
        app._on_message(topics.AGENT_TURN_ERROR, {"message": "x", "class": "harness"})
        app._on_message(topics.AGENT_DELTA, {"index": 0, "kind": "text", "text": "hi"})
        assert app.ui.overlay == ""


class TestSubscriptions:
    def test_subscribes_to_every_watched_topic(self):
        bridge = FakeBridge()
        app = _app(bridge)
        asyncio.run(app._subscribe_all())
        assert set(bridge.subscribed) == set(WATCHED_TOPICS)

    def test_does_not_resubscribe_when_already_subscribed(self):
        """The bridge replays subscriptions on reconnect; a second subscribe
        would register a duplicate forwarder and double every message."""
        bridge = FakeBridge()
        app = _app(bridge)
        asyncio.run(app._subscribe_all())
        first = list(bridge.subscribed)
        asyncio.run(app._subscribe_all())
        assert bridge.subscribed == first


class TestNoQt:
    def test_importing_the_tui_pulls_no_qt(self):
        import subprocess
        import sys

        code = (
            "import sys; import aiassistant.tui.app; "
            "print('PySide6' in sys.modules)"
        )
        result = subprocess.run([sys.executable, "-c", code],
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "False"


class TestHelpHotword:
    """The TUI help overlay names the configured wake phrase."""

    def test_help_line_names_the_hotword(self):
        from aiassistant.tui.render import Renderer
        r = Renderer(identity="Jarvis", hotwords=["hey jarvis"])
        assert 'say "hey jarvis"' in r._help_lines()[0]

    def test_help_omits_the_line_when_unconfigured(self):
        from aiassistant.tui.render import Renderer
        r = Renderer(identity="Jarvis", hotwords=[])
        assert not r._hotword_line()
        assert not any("Hotword" in line for line in r._help_lines())

    def test_help_width_fits_the_longest_line(self):
        from aiassistant.tui.render import Renderer
        r = Renderer(hotwords=["a very long wake phrase indeed"])
        assert max(len(line) for line in r._help_lines()) <= 200

    def test_config_supplies_hotwords_to_the_app(self):
        from aiassistant.tui.app import TuiApp
        app = TuiApp(url="ws://127.0.0.1:1", token="", identity="J",
                     bridge=FakeBridge(), hotwords=["hey jarvis"])
        assert app.renderer.hotwords == ["hey jarvis"]
