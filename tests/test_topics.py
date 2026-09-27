"""Topic constants and payload schema tests.

These guard the interface that has no compiler support. The specific regression
being prevented: routing decisions were made by comparing bare strings inline
(for example the TTS trigger compared ``source == "ears"``), so renaming a module
silently disabled speech.
"""

import pytest

from aiassistant.bus import topics


class TestTopicConstants:
    def test_no_duplicate_values(self):
        """Two constants sharing a value would make routing ambiguous."""
        values = {
            name: value
            for name, value in vars(topics).items()
            if name.isupper() and isinstance(value, str)
        }
        seen: dict[str, str] = {}
        for name, value in values.items():
            assert value not in seen, f"{name} and {seen[value]} share the value {value!r}"
            seen[value] = name

    def test_topic_values_are_dotted_strings(self):
        """Topic constants are dotted; channel constants are bare labels."""
        for name, value in vars(topics).items():
            if not name.isupper() or not isinstance(value, str):
                continue
            if name.startswith("CHANNEL_"):
                continue
            assert value == value.strip(), f"{name} has surrounding whitespace"
            assert "." in value, f"{name}={value!r} is not a dotted topic"
            assert " " not in value, f"{name}={value!r} contains a space"

    def test_channel_values_are_bare_labels(self):
        for name, value in vars(topics).items():
            if name.startswith("CHANNEL_"):
                assert value.islower(), f"{name}={value!r} should be a bare lowercase label"


class TestChannelRouting:
    """topics.should_speak is the single source of truth for speech routing."""

    def test_voice_channel_speaks(self):
        assert topics.should_speak(topics.CHANNEL_VOICE) is True

    def test_non_voice_channels_do_not_speak(self):
        for channel in (
            topics.CHANNEL_ORB,
            topics.CHANNEL_CONSOLE,
            topics.CHANNEL_SCHEDULE,
            topics.CHANNEL_MESSAGING,
        ):
            assert topics.should_speak(channel) is False

    def test_unknown_channel_does_not_speak(self):
        """Default to silence: an unknown channel must never surprise the user
        by talking."""
        assert topics.should_speak("") is False
        assert topics.should_speak("something-new") is False

    def test_speaking_channels_is_the_source_of_truth(self):
        for channel in topics.SPEAKING_CHANNELS:
            assert topics.should_speak(channel) is True
