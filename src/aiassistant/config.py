"""Configuration loading: precedence and legacy-key migration.

Precedence (REQ-CFG-002): CLI override > environment > config file > defaults.

Legacy keys from the pre-refactor config are accepted, mapped to their new
names, and reported once as deprecated (REQ-CFG-004). The mapping lives in
``LEGACY_*`` tables so it is testable in isolation and cannot rot silently.
"""

import logging

logger = logging.getLogger(__name__)

# Old top-level section -> new top-level section.
LEGACY_SECTIONS = {
    "brain": "agent",
    "ears": "voice",
    "mouth": "voice_tts",
    "hands": "tools",
    "eyes": "vision",
    "chat": "messaging",
    "cli": "console",
}

# Sections that no longer exist at all.
REMOVED_SECTIONS = {"canvas"}

# Old key -> new key, within the mapped section.
LEGACY_KEYS = {
    "voice": {"recognizer": "recognizer", "hotwords": "hotwords"},
}

# Units or names that differ between old and new.
# ears.silence_timeout is seconds; the new key is milliseconds.
LEGACY_SCALE = {
    ("voice", "silence_timeout"): ("endpoint_silence_ms", 1000),
}


def migrate_legacy(config: dict) -> dict:
    """Rewrite legacy keys in place and return the same dict.

    Unknown legacy sections are dropped with a warning rather than passed
    through, so downstream modules never see a section they do not expect.
    """
    for old, new in LEGACY_SECTIONS.items():
        if old not in config:
            continue
        section = config.pop(old)
        logger.warning("Config section %r is deprecated; use %r", old, new)
        if isinstance(section, dict):
            target = config.setdefault(new, {})
            for key, value in section.items():
                mapped = LEGACY_KEYS.get(new, {}).get(key, key)
                scaled = LEGACY_SCALE.get((new, key))
                if scaled:
                    new_key, factor = scaled
                    value = int(value) * factor
                    mapped = new_key
                target.setdefault(mapped, value)

    for removed in REMOVED_SECTIONS:
        if removed in config:
            config.pop(removed)
            logger.warning("Config section %r was removed; ignoring it", removed)

    return config


def apply_overrides(config: dict, overrides: dict) -> None:
    """Apply dotted-key overrides, creating intermediate dicts as needed."""
    for dotted_key, value in overrides.items():
        parts = dotted_key.split(".")
        target = config
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value
