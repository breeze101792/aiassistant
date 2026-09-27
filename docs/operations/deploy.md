# Operations — Deploy and Release

There is no server deployment. This covers packaging the desktop app and
releasing the code.

## Packaging the orb

Use `pyside6-deploy` (Nuitka-backed) on each target OS separately.

```sh
pyside6-deploy orb/main.py
```

| OS | Output | Notes |
| --- | --- | --- |
| macOS | `.app` bundle | Notarization is separate work, not on the MVP path |
| Linux | AppImage or a distro package | Test against the target distribution |

## PySide6 licensing (LGPLv3)

Distribution obligations:

1. **Dynamic linking** — do not statically link Qt.
2. **Notice** — state that the app uses Qt under LGPLv3 and where to get it.
3. **Relink capability** — the user must be able to replace the Qt libraries.

Satisfied by shipping PySide6 as a separate, replaceable library directory. If a
locked-down single-binary build is ever required, re-evaluate against a Qt
commercial license.

## Release checklist

- [ ] `pytest` passes on macOS and Linux.
- [ ] Manual smoke on both OSes: launch, voice turn, orb animates, interrupt
      works, console fallback works.
- [ ] `docs/` updated to as-built for anything that changed.
- [ ] `testing/trace.md` still shows every REQ covered or explicitly unverified.
- [ ] No secret in the checked-in `config.yaml` (REQ-CFG-005).
- [ ] Version bumped in one place.

## Versioning

Application version lives in `pyproject.toml`. The interfaces that change
independently are the **bus topics** and the **harness contract**; a breaking
change to either is a minor-version bump with a migration note, because
out-of-process clients (the orb) depend on them.

## Rollback

The state that matters is user data: markdown memory, `embeddings.db` (a
rebuildable cache), and `schedules.json`. All live under `.config/aiassistant/`
or the configured paths, so a rollback is a code downgrade plus, if needed,
restoring that directory. The embeddings cache can be deleted and rebuilt at any
time.
