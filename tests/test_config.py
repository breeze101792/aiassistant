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
