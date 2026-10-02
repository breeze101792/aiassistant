"""Conversational talk: the voice pipeline must behave like a natural exchange.

Each test here pins one property of the recent fix, end to end through the real
FSM and the wake-window path, with injected frames and a fake ASR. No device is
opened and no model is called.

The five properties:
  1. No manual unmute between turns: half-duplex mutes while speaking and the
     module settles in ``idle`` with a live mic, so the next utterance is
     accepted with no Ctrl+T.
  2. Wake mode: the phrase alone opens a follow-up window; an utterance inside
     it needs no phrase; a spoken reply refreshes the window; quiet closes it;
     an explicit mute closes it.
  3. ``open`` mode: every utterance is a turn.
  4. The system prompt is conversational and forbids emoji.
  5. The TUI empty-state phrase comes from config, never a hardcoded literal.
"""

import pytest

from aiassistant.agent.persona import Persona
from aiassistant.bus.bus import MessageBus
from aiassistant.config import DEFAULTS
from aiassistant.tui.render import Renderer
from aiassistant.voice.state import VoiceState

from conftest import build_voice_session

# A short window keeps the timeout test fast; long enough that the task does not
# fire before the test drives the next utterance.
WAKE_WINDOW_MS = 3000

# A window short enough that waiting for its timeout is quick but still bounded.
SHORT_WAKE_WINDOW_MS = 120


def _contains_emoji(text: str) -> bool:
    """Whether ``text`` contains any emoji-range code point."""
    import unicodedata
    for ch in text:
        if ord(ch) >= 0x1F000:
            return True
        if unicodedata.category(ch) == "So":
            return True
    return False


class TestNoManualUnmute:
    """Property 1: a reply leaves the mic live and the FSM idle."""

    @pytest.mark.asyncio
    async def test_second_utterance_is_accepted_without_a_manual_unmute(
            self, voice_session):
        assert voice_session.mod.listen_mode == "open"

        voice_session.speak("turn on the light")
        assert voice_session.turns == ["turn on the light"]

        await voice_session.reply()
        # The mic is gated briefly after speech so the speaker tail is not
        # captured; it reopens on its own once the guard elapses.
        assert await voice_session.wait_for_mic_live(), (
            "half-duplex must restore the mic after the echo guard"
        )
        assert voice_session.mod._user_muted is False, (
            "the transient speaking mute must never be recorded as a user mute"
        )
        assert voice_session.mod._state.state is VoiceState.IDLE

        # A second utterance right after the reply, with no Ctrl+T.
        voice_session.speak("now turn it off")
        assert voice_session.turns == ["turn on the light", "now turn it off"]

    @pytest.mark.asyncio
    async def test_speaking_end_publishes_idle_with_a_live_mic(self, voice_session):
        voice_session.speak("hello")
        await voice_session.reply()
        assert await voice_session.wait_for_mic_live()

        assert voice_session.mod.capture.muted is False
        assert voice_session.mod._state.state is VoiceState.IDLE
        # The last published state is the one the UI settles on.
        assert voice_session.states[-1]["state"] == "idle"
        assert voice_session.states[-1]["muted"] is False

    @pytest.mark.asyncio
    async def test_the_echo_guard_gates_the_mic_then_reopens_it(
            self, voice_session):
        """The assistant must not hear its own tail and start a turn.

        Right after playback the mic stays gated for the guard window, then
        reopens by itself.
        """
        voice_session.speak("hello")
        await voice_session.reply()

        assert voice_session.mod.capture.muted is True, (
            "the mic must stay gated right after playback"
        )
        assert await voice_session.wait_for_mic_live(), (
            "the guard must release when the tail has died away"
        )

    @pytest.mark.asyncio
    async def test_no_idle_and_muted_pair_is_ever_published(self, voice_session):
        """The UI must never flash the mute indicator between turns.

        The guard is internal: the published ``muted`` flag reports the user's
        intent, never the half-duplex or echo gate.
        """
        voice_session.speak("hello")
        await voice_session.reply()
        await voice_session.wait_for_mic_live()
        voice_session.speak("again")
        await voice_session.reply()
        await voice_session.wait_for_mic_live()

        assert voice_session.idle_muted_pairs() == []

    @pytest.mark.asyncio
    async def test_half_duplex_still_mutes_while_speaking(self, voice_session):
        voice_session.speak("hello")
        voice_session.mod._transition_quietly(VoiceState.THINKING)
        voice_session.mod._transition_quietly(VoiceState.SPEAKING)

        assert voice_session.mod.capture.muted is True, (
            "the mic must be gated while speaking"
        )
        voice_session.mod._enter_idle()
        assert await voice_session.wait_for_mic_live()


class TestOpenMode:
    """Property 3: every utterance is a turn."""

    @pytest.mark.asyncio
    async def test_two_consecutive_utterances_produce_two_turns(self, voice_session):
        voice_session.speak("first")
        assert voice_session.turns == ["first"]

        await voice_session.reply()
        voice_session.speak("second")

        assert voice_session.turns == ["first", "second"]

    @pytest.mark.asyncio
    async def test_open_mode_needs_no_wake_phrase(self, voice_session):
        voice_session.speak("what is the weather")
        assert voice_session.turns == ["what is the weather"]

    @pytest.mark.asyncio
    async def test_injected_frames_become_a_turn_end_to_end(self, voice_session):
        """The real audio path, not just ``_publish_transcript``.

        Frames go through VAD, the segmenter, the ASR worker, and the transcript
        path. No device and no model: the ASR is a fake.
        """
        await voice_session.feed_utterance()

        assert voice_session.turns == [voice_session.asr.text]
        assert voice_session.asr.pcm, "the ASR worker must receive the utterance"
        assert voice_session.mod._state.state is VoiceState.THINKING


class TestWakeModeFlow:
    """Property 2: the follow-up window."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("voice_session",
                             [{"mode": "wake", "wake_window_ms": WAKE_WINDOW_MS}],
                             indirect=True)
    async def test_phrase_only_opens_the_window_with_no_turn(self, voice_session):
        voice_session.speak("hey jarvis")

        assert voice_session.turns == [], "the phrase alone is not a command"
        assert voice_session.mod._wake_active is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("voice_session",
                             [{"mode": "wake", "wake_window_ms": WAKE_WINDOW_MS}],
                             indirect=True)
    async def test_follow_up_inside_the_window_needs_no_phrase(self, voice_session):
        voice_session.speak("hey jarvis")
        assert voice_session.mod._wake_active is True

        voice_session.speak("turn on the light")
        assert voice_session.turns == ["turn on the light"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("voice_session",
                             [{"mode": "wake", "wake_window_ms": WAKE_WINDOW_MS}],
                             indirect=True)
    async def test_a_spoken_reply_refreshes_the_window(self, voice_session):
        voice_session.speak("hey jarvis")
        voice_session.speak("first command")
        assert voice_session.turns == ["first command"]

        # The assistant answers and finishes playback. The window must survive.
        await voice_session.reply()
        assert voice_session.mod._wake_active is True, (
            "the window must be refreshed when playback finishes"
        )

        voice_session.speak("second command")
        assert voice_session.turns == ["first command", "second command"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("voice_session",
                             [{"mode": "wake", "wake_window_ms": SHORT_WAKE_WINDOW_MS}],
                             indirect=True)
    async def test_the_window_closes_after_quiet(self, voice_session):
        voice_session.speak("hey jarvis")
        assert voice_session.mod._wake_active is True

        closed = await voice_session.wait_for_wake_window(False)
        assert closed, "the window must close after wake_window_ms of quiet"

        voice_session.speak("turn on the light")
        assert voice_session.turns == [], (
            "after the window closes the wake phrase is required again"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("voice_session",
                             [{"mode": "wake", "wake_window_ms": WAKE_WINDOW_MS}],
                             indirect=True)
    async def test_an_explicit_mute_closes_the_window(self, voice_session):
        voice_session.speak("hey jarvis")
        assert voice_session.mod._wake_active is True

        voice_session.mute(True)
        assert voice_session.mod._wake_active is False, (
            "an explicit mute must end the follow-up window"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("voice_session",
                             [{"mode": "wake", "wake_window_ms": WAKE_WINDOW_MS}],
                             indirect=True)
    async def test_a_user_mute_survives_a_reply_cycle(self, voice_session):
        voice_session.mute(True)
        assert voice_session.mod.capture.muted is True

        # Walk a reply while the user mute is set; it must stick.
        voice_session.mod._transition_quietly(VoiceState.LISTENING)
        voice_session.mod._transition_quietly(VoiceState.THINKING)
        voice_session.mod._transition_quietly(VoiceState.SPEAKING)
        voice_session.mod._enter_idle()

        assert voice_session.mod._state.state is VoiceState.MUTED
        assert voice_session.mod.capture.muted is True, (
            "a user mute must survive the reply cycle"
        )


class TestPersonaIsConversational:
    """Property 4: the default persona is a conversational voice assistant."""

    def test_default_prompt_states_the_conversational_intent(self):
        prompt = Persona().get_system_prompt()
        lowered = prompt.lower()
        assert "conversational" in lowered
        assert "voice assistant" in lowered

    def test_default_prompt_forbids_emoji(self):
        prompt = Persona().get_system_prompt().lower()
        assert "emoji" in prompt, "the prompt must tell the model not to use emoji"
        assert _contains_emoji(Persona().get_system_prompt()) is False

    def test_default_prompt_caps_the_reply_length(self):
        """Replies must stay short: one paragraph, five sentences at most."""
        prompt = Persona().get_system_prompt().lower()
        assert "five sentences" in prompt
        assert "five" in prompt and "sentence" in prompt

    def test_config_default_also_caps_the_reply_length(self):
        assert "five sentences" in DEFAULTS["agent"]["persona"].lower()

    def test_config_default_matches_the_persona(self):
        configured = DEFAULTS["agent"]["persona"]
        assert "conversational" in configured.lower()
        assert _contains_emoji(configured) is False

    def test_persona_name_is_the_assistant_name(self):
        name = Persona().name
        assert name == "Jarvis"
        # Not an awkward fragment of the intent sentence.
        assert not name.lower().startswith("a conversational")


class TestTuiEmptyState:
    """Property 5: the empty-state phrase comes from config."""

    def test_empty_state_names_the_configured_phrase(self):
        renderer = Renderer(hotwords=["hey jarvis"])
        text = renderer._empty_text()
        assert '"hey jarvis"' in text
        assert "hi jarvis" not in text

    def test_empty_state_tracks_a_different_configured_phrase(self):
        renderer = Renderer(hotwords=["computer"])
        assert '"computer"' in renderer._empty_text()
        assert "hi jarvis" not in renderer._empty_text()

    def test_empty_state_uses_the_config_default_hotword(self):
        renderer = Renderer(hotwords=DEFAULTS["voice"]["hotwords"])
        assert f'"{DEFAULTS["voice"]["hotwords"][0]}"' in renderer._empty_text()

    def test_empty_state_without_a_hotword_omits_the_say_clause(self):
        assert Renderer(hotwords=[])._empty_text() == (
            "No messages yet. Type below."
        )


class TestWakeModeGating:
    """`wake` mode must ignore speech that does not contain the phrase.

    Reported as "the hotword detect fails; it speaks what it listens". The cause
    was `listen.mode: open`, where the detector accepts everything by design. In
    `wake` mode the phrase is required, and the phrase is stripped from the
    command.
    """

    @pytest.mark.asyncio
    async def test_wake_mode_ignores_speech_without_the_phrase(self):
        bus = MessageBus()
        session = build_voice_session(bus, mode="wake")
        await session.setup()
        await session.start()
        try:
            session.speak("what is the weather")
            assert session.turns == [], (
                "without the wake phrase the turn must be ignored"
            )
        finally:
            await session.stop()

    @pytest.mark.asyncio
    async def test_wake_mode_accepts_speech_with_the_phrase_and_strips_it(self):
        bus = MessageBus()
        session = build_voice_session(bus, mode="wake")
        await session.setup()
        await session.start()
        try:
            session.speak("hey jarvis what is the weather")
            assert session.turns == ["what is the weather"], (
                "the phrase is a gate and is removed from the command"
            )
        finally:
            await session.stop()

    @pytest.mark.asyncio
    async def test_open_mode_accepts_speech_without_the_phrase(self):
        """`open` is always-listening by design: no phrase is required."""
        bus = MessageBus()
        session = build_voice_session(bus, mode="open")
        await session.setup()
        await session.start()
        try:
            session.speak("what is the weather")
            assert session.turns == ["what is the weather"]
        finally:
            await session.stop()
