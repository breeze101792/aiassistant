"""Config model tests: code defaults, the local file, and legacy migration.

Defaults live in code, so the assistant runs with no config file. `config.yaml`
is a local override that names only what differs. `config.example.yaml` is the
tracked example and must stay in step with the defaults, so a user copying it
gets exactly what runs (REQ-CFG-008).
"""

import os

import pytest
import yaml

from aiassistant import config as config_mod
from aiassistant.config import (
    DEFAULTS,
    load_config,
    load_config_file,
    merge_config,
    migrate_legacy,
)

EXAMPLE_PATH = os.path.join(os.path.dirname(config_mod.__file__), "..", "..", "..",
                            "config.example.yaml")
REPO_EXAMPLE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "config.example.yaml"))


class TestDefaultsInCode:
    def test_runs_with_no_config_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = load_config()
        assert cfg["bus"]["websocket_port"] == 8765
        assert cfg["agent"]["harness"] == "native"

    def test_missing_file_yields_the_defaults(self, tmp_path):
        cfg = load_config(str(tmp_path / "nope.yaml"))
        assert cfg == DEFAULTS

    def test_local_file_overrides_only_its_keys(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text("bus:\n  websocket_port: 9999\n")
        cfg = load_config(str(p))
        assert cfg["bus"]["websocket_port"] == 9999
        assert cfg["bus"]["bind"] == "127.0.0.1"          # untouched default
        assert cfg["agent"]["llm"]["model"] == DEFAULTS["agent"]["llm"]["model"]

    def test_local_file_may_add_a_new_section(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text("display:\n  mode: none\n")
        cfg = load_config(str(p))
        assert cfg["display"]["mode"] == "none"
        assert cfg["display"]["always_on_top"] is True

    def test_malformed_file_falls_back_to_defaults(self, tmp_path, caplog):
        p = tmp_path / "config.yaml"
        p.write_text("bus: [unclosed\n")
        cfg = load_config(str(p))
        assert cfg["bus"]["websocket_port"] == 8765

    def test_load_does_not_mutate_the_defaults(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text("bus:\n  websocket_port: 1\n")
        load_config(str(p))
        assert DEFAULTS["bus"]["websocket_port"] == 8765


class TestMerge:
    def test_nested_keys_merge(self):
        base = {"agent": {"harness": "native", "llm": {"model": "a", "url": "u"}}}
        merge_config(base, {"agent": {"llm": {"model": "b"}}})
        assert base["agent"]["llm"] == {"model": "b", "url": "u"}

    def test_scalar_replaces(self):
        base = {"conversation": {"busy": "interrupt"}}
        merge_config(base, {"conversation": {"busy": "queue"}})
        assert base["conversation"]["busy"] == "queue"

    def test_list_replaces_not_appends(self):
        base = {"voice": {"hotwords": ["a", "b"]}}
        merge_config(base, {"voice": {"hotwords": ["c"]}})
        assert base["voice"]["hotwords"] == ["c"]


class TestLegacyMigration:
    """REQ-CFG-004: old section keys are accepted, warned, and mapped.

    schemas.md:275-290 names every rename. A top-level-only map would silently
    drop a real user's config, so each section and the unit-bearing key is
    pinned here.
    """

    def test_section_renames_are_mapped(self):
        raw = {
            "brain": {"persona": "X"},
            "ears": {"backend": "whisper"},
            "mouth": {"backend": "edge_tts"},
            "hands": {"sandbox_default": True},
            "eyes": {"backend": "opencv"},
            "chat": {"telegram_token": "t"},
            "cli": {"prompt": "$ "},
        }
        migrated = migrate_legacy(dict(raw))
        assert migrated["agent"]["persona"] == "X"
        assert migrated["voice"]["asr"]["backend"] == "whisper"
        assert migrated["voice"]["tts"]["backend"] == "edge_tts"
        assert migrated["tools"]["sandbox_default"] is True
        assert migrated["vision"]["backend"] == "opencv"
        assert migrated["messaging"]["telegram_token"] == "t"
        assert migrated["console"]["prompt"] == "$ "
        assert not (set(raw) & set(migrated)), "legacy sections are consumed"

    def test_nested_legacy_keys_keep_their_mapping(self):
        migrated = migrate_legacy(dict({
            "brain": {"llm": {"model": "m1", "provider": "openai"}},
        }))
        assert migrated["agent"]["llm"] == {"model": "m1", "provider": "openai"}

    def test_silence_timeout_unit_is_scaled_to_ms(self):
        """``ears.silence_timeout`` is seconds; the new key is milliseconds."""
        migrated = migrate_legacy(dict({"ears": {"silence_timeout": 3}}))
        assert migrated["voice"]["endpoint_silence_ms"] == 3000

    def test_removed_section_is_dropped(self):
        migrated = migrate_legacy(dict({"canvas": {"web_port": 1}}))
        assert "canvas" not in migrated

    def test_a_new_key_wins_over_a_legacy_one(self):
        """``setdefault`` keeps the canonical section when both are present."""
        migrated = migrate_legacy(dict({
            "agent": {"persona": "new"},
            "brain": {"persona": "old"},
        }))
        assert migrated["agent"]["persona"] == "new"


class TestAudioPipelineMigration:
    """ADR-0018 migrated the flat voice keys to per-stage sections.

    The old value survives migration verbatim, including ``halasr``, so the
    factory can report the removal error instead of a user silently getting the
    stub. Each row is pinned here because a top-level-only map would drop a real
    user's config.
    """

    @pytest.mark.parametrize("legacy", ["stub", "whisper", "funasr"])
    def test_voice_backend_moves_to_voice_asr_backend(self, legacy):
        migrated = migrate_legacy(dict({"voice": {"backend": legacy}}))
        assert migrated["voice"]["asr"]["backend"] == legacy
        assert "backend" not in migrated["voice"], "the flat key is consumed"

    def test_ears_backend_composes_with_the_move(self):
        """``ears`` -> ``voice``, then ``voice.backend`` -> ``voice.asr.backend``."""
        migrated = migrate_legacy(dict({"ears": {"backend": "whisper"}}))
        assert migrated["voice"]["asr"]["backend"] == "whisper"

    def test_recognizer_is_dropped_not_migrated(self, caplog):
        from aiassistant.config import migrate_legacy

        with caplog.at_level("WARNING"):
            migrated = migrate_legacy(dict({"voice": {"recognizer": "whisper"}}))
        assert "recognizer" not in migrated["voice"]
        assert migrated["voice"] == {}
        assert any("recognizer" in record.message for record in caplog.records), (
            "dropping a key must warn, not silently discard"
        )

    def test_halasr_survives_migration_for_the_factory_to_reject(self):
        """The factory, not the migrator, owns the ADR-0018 hard error."""
        from aiassistant.voice.factory import VoiceConfigError, create_asr

        migrated = migrate_legacy(dict({"voice": {"backend": "halasr"}}))
        assert migrated["voice"]["asr"]["backend"] == "halasr"
        with pytest.raises(VoiceConfigError, match="removed in ADR-0018"):
            create_asr(migrated["voice"]["asr"])

    def test_voice_tts_section_moves_to_voice_tts(self):
        migrated = migrate_legacy(dict({
            "voice_tts": {"backend": "text", "voice": "v", "speed": 1.5},
        }))
        assert migrated["voice"]["tts"] == {
            "backend": "text", "voice": "v", "speed": 1.5,
        }
        assert "voice_tts" not in migrated, "the superseded section is dropped"

    def test_mouth_backend_composes_with_the_move(self):
        migrated = migrate_legacy(dict({"mouth": {"backend": "text"}}))
        assert migrated["voice"]["tts"]["backend"] == "text"

    def test_silence_timeout_scales_to_endpoint_silence_ms(self):
        """``ears.silence_timeout`` is seconds; the new key is milliseconds."""
        migrated = migrate_legacy(dict({"ears": {"silence_timeout": 3}}))
        assert migrated["voice"]["endpoint_silence_ms"] == 3000

    def test_endpoint_silence_ms_is_the_segmenter_source(self):
        """The module reads ``voice.endpoint_silence_ms`` into the segmenter."""
        from aiassistant.bus.bus import MessageBus
        from aiassistant.voice.module import VoiceModule

        raw = migrate_legacy(dict({"ears": {"silence_timeout": 3}}))
        mod = VoiceModule(MessageBus(), {"voice": {"backend": "stub",
                                                   **raw["voice"]}})
        assert mod.endpoint_silence_ms == 3000

    def test_a_new_stage_key_wins_over_a_legacy_one(self, caplog):
        migrated = migrate_legacy(dict({
            "voice": {"asr": {"backend": "funasr"}, "backend": "whisper"},
        }))
        assert migrated["voice"]["asr"]["backend"] == "funasr"

    def test_the_canonical_sections_are_all_present_in_defaults(self):
        for stage in ("vad", "segmenter", "asr", "tts"):
            assert stage in DEFAULTS["voice"], stage



class TestAgentsMap:
    """REQ-CFG-006: the ``agents:`` map defines one or more identities.

    schemas.md:200-223 and data-model.md describe an ``agents:`` map with
    ``agents.active``. The ``DEFAULTS`` and every module read the singular
    ``agent`` section instead, so a config written to the documented shape is
    ignored. Pinned as an xfail, not silently accepted.
    """

    def test_single_agent_section_still_works(self):
        from aiassistant.agent.module import AgentModule
        from aiassistant.bus.bus import MessageBus

        mod = AgentModule(MessageBus(), {"agent": {"persona": "I am X"}})
        assert "I am X" in mod.persona.get_system_prompt()

    @pytest.mark.xfail(strict=True,
                       reason="BUG-7: schemas.md documents an agents: map with "
                              "agents.active, but AgentModule reads only the "
                              "singular agent section")
    def test_documented_agents_map_supplies_the_active_agent(self):
        from aiassistant.agent.module import AgentModule
        from aiassistant.bus.bus import MessageBus

        mod = AgentModule(MessageBus(), {
            "agents": {
                "active": "jarvis",
                "jarvis": {
                    "harness": "native",
                    "persona": "I am Jarvis",
                    "llm": {"provider": "openai", "model": "gpt-x"},
                },
            },
        })
        assert "I am Jarvis" in mod.persona.get_system_prompt()
        assert mod.llm_config.get("model") == "gpt-x"


class TestExampleMatchesDefaults:
    """config.example.yaml is the documented view of DEFAULTS.

    If these drift, the example lies to the user. This is the guard that keeps
    the file honest, so it can be edited but not quietly outgrown.
    """

    def test_example_file_exists(self):
        assert os.path.isfile(REPO_EXAMPLE), REPO_EXAMPLE

    def test_example_parses(self):
        raw = yaml.safe_load(open(REPO_EXAMPLE))
        assert isinstance(raw, dict)

    def test_example_keys_are_all_real_defaults(self):
        raw = yaml.safe_load(open(REPO_EXAMPLE))

        def walk(example, defaults, path=""):
            for key, value in example.items():
                here = f"{path}.{key}" if path else key
                assert key in defaults, f"{here} is not a default key"
                if isinstance(value, dict):
                    assert isinstance(defaults[key], dict), f"{here} is not a section"
                    walk(value, defaults[key], here)

        walk(raw, DEFAULTS)

    def test_every_default_key_is_documented(self):
        """A default missing from the example is invisible to the user."""
        raw = yaml.safe_load(open(REPO_EXAMPLE))

        def walk(defaults, example, path=""):
            for key, value in defaults.items():
                here = f"{path}.{key}" if path else key
                assert key in example, f"{here} is missing from config.example.yaml"
                if isinstance(value, dict):
                    walk(value, example[key], here)

        walk(DEFAULTS, raw)

    def test_example_values_match_the_defaults(self):
        raw = yaml.safe_load(open(REPO_EXAMPLE))

        def compare(example, defaults, path=""):
            for key, value in example.items():
                here = f"{path}.{key}" if path else key
                if isinstance(value, dict):
                    compare(value, defaults[key], here)
                else:
                    assert value == defaults[key], (
                        f"{here}: example has {value!r}, default is {defaults[key]!r}")


        compare(raw, DEFAULTS)
