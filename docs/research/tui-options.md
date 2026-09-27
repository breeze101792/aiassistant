# TUI for aiassistant — Research Findings

**Question:** what are the established facts needed to choose and build a
terminal user interface for this project, among stdlib `curses`, `rich`, and
`textual`?

**Scope:** this report establishes facts. It does not choose a library and does
not contain application code. The selection belongs to `plan`/`architect`.

**Evidence labels used throughout:**

- `[DOC]` — read directly from official documentation or upstream source.
- `[EXPT]` — observed by running a command in this environment.
- `[INF]` — a conclusion drawn from `[DOC]`/`[EXPT]`; not itself read.
- `[U]` — not established by the sources I could read.

**Versions in play (confirmed from the project and the running interpreter):**

| Item | Value | Source |
| --- | --- | --- |
| Project Python floor | `>=3.11` | `pyproject.toml:9` |
| Interpreter used for experiments | 3.13.15 | `python3 --version`, this shell |
| Project dependencies | no `curses`, `rich`, or `textual` declared; `curses` is stdlib | `pyproject.toml:11-29` |
| `curses` docs read | 3.11.16 and 3.14.7 | docs.python.org |
| `rich` (latest on PyPI, measured) | 15.0.0 | PyPI JSON; venv `importlib.metadata` |
| `textual` (latest on PyPI, measured) | 8.2.8 | PyPI JSON; venv `importlib.metadata` |
| `windows-curses` (latest) | 2.4.2 | PyPI JSON |

---

## 1. Availability and platform

**Finding.** `curses` is part of the Python standard library on Linux and
macOS, but it is an **optional** stdlib module that is **not bundled inside
CPython**: it is a C extension linked at build time against a system
`libncurses`/`libncursesw`. On Unix, a normal distribution build has it; a
build without the ncurses headers does not.

**Evidence.**

- `[DOC]` The 3.14 `curses` page states: "This is an optional module. If it is
  missing from your copy of CPython, look for documentation from your
  distributor", and gives "Availability: Unix" plus "not Android, not iOS, not
  WASI". It also states the module "is designed to match the API of ncurses, an
  open-source curses library hosted on Linux and the BSD variants of Unix."
  (https://docs.python.org/3.14/library/curses.html, module intro.)
- `[DOC]` The CPython configure documentation's "Requirements for optional
  modules" table lists `ncurses` as the dependency for the `curses` module, with
  the footnote "The `curses` module requires the `libncurses` or `libncursesw`
  library. The `curses.panel` module additionally requires the `libpanel` or
  `libpanelw` library." The 3.11 edition of the same page has the equivalent
  entries (`CURSES_CFLAGS` / `CURSES_LIBS` "for `libncurses` or `libncursesw`,
  used by `curses` module").
  (https://docs.python.org/3/using/configure.html#requirements-for-optional-modules;
  3.11: https://docs.python.org/3.11/using/configure.html)
- `[DOC]` CPython 3.11's `setup.py` `detect_readline_curses()` probes for
  `ncursesw`, then `ncurses`, then `curses`, and only builds `_curses` when a
  library is found (`Modules/_cursesmodule.c` linked against it).
  (https://raw.githubusercontent.com/python/cpython/3.11/setup.py, lines ~1079-1090.)
- `[EXPT]` On this machine (Python 3.13.15), `import curses` succeeds;
  `curses.setupterm()` with `TERM=xterm-256color` succeeds and
  `curses.tigetnum("colors")` returns `256`. So the module is present in this
  distribution.

**Platform notes.**

- **Linux:** present in distribution builds; absent only in a stripped build.
  `[DOC]` above + `[EXPT]` here.
- **macOS:** `[INF]` the same "Unix + libncurses" rule applies. macOS ships an
  ncurses, so the python.org and Homebrew Pythons and the system Python
  normally have `curses`. `[U]` I did not read an Apple or python.org primary
  page that states this explicitly. A known failure mode is a **pyenv-built**
  Python whose `_curses` extension was not compiled because the ncurses headers
  were not on the build path — a user report, not an official doc, so `[U]`.
  Practical consequence: a from-source Python can lack `curses`; a pip-installed
  wheel cannot add it (there is no pip fallback for the extension itself).
- **Windows:** `[DOC]` the stdlib module is Unix-only ("Availability: Unix").
  `[DOC]` PyPI's `windows-curses` 2.4.2 is a separate package ("Support for the
  standard curses module on Windows", license PSF2) that supplies it. The
  project does not target Windows (`pyproject.toml:9-10`; `docs/ui/README.md:41`
  "macOS 13+ and current Linux"), so this is out of scope but stated for
  completeness.

**Consequence for the project.** `curses` being stdlib removes a *pip*
dependency, but not a *build* dependency: it can be absent, and it needs a
usable terminfo/TERM at runtime (see §3). No wheel can repair a Python built
without it.

---

## 2. A fuller TUI vs stdlib curses — the comparison

All three render to a character terminal. The differences that matter here are
dependency weight, whether a real tty is required, SSH behavior, "dumb"
terminal behavior, and non-tty fallback.

| Dimension | `curses` (stdlib) | `rich` 15.0.0 | `textual` 8.2.8 |
| --- | --- | --- | --- |
| **What it is** | Low-level C binding to ncurses; you manage windows, refresh, input | Terminal *rendering* library (tables, panels, live, markdown, syntax); not a full-screen app framework by default | Full TUI **application** framework built on Rich; own asyncio event loop, DOM, CSS, widgets |
| **Dependency weight** | 0 pip deps; requires a system ncurses and a working TERM `[DOC]` configure page; `[EXPT]` works here | Pure Python; `[DOC]` PyPI requires `markdown-it-py>=2.2.0`, `pygments>=2.13.0` | `[DOC]` PyPI requires `markdown-it-py[linkify]>=2.1.0`, `mdit-py-plugins`, `platformdirs`, `pygments`, `rich>=14.2.0`, `typing-extensions` |
| **Measured install footprint** | none (stdlib) | `[EXPT]` in a clean venv, rich pulls `markdown-it-py`, `mdurl`, `pygments` | `[EXPT]` clean-venv `pip install textual` produced 9 new distributions: textual, rich, markdown-it-py, mdit-py-plugins, mdurl, linkify-it-py, platformdirs, pygments, typing_extensions |
| **License** | PSF (CPython) `[DOC]` | MIT `[DOC]` (PyPI license field) | MIT `[DOC]` (PyPI license field) |
| **Needs a real tty?** | Yes for full-screen use; `initscr()` emits escape sequences regardless (see §3) | No: degrades to plain text when `is_terminal` is False `[DOC]/[EXPT]` | Yes for full-screen application mode; writes escapes to `sys.__stderr__` even when output is redirected (see §3) |
| **Works over SSH?** | Yes when a pty is allocated | Yes | Yes |
| **`TERM=dumb`** | `setupterm()` succeeds but `colors=-1`, `cup=None`, `clear=None` — no cursor addressing `[EXPT]` | Disables color/style and cursor-moving features `[DOC]` | Not special-cased; `[EXPT]` still writes application-mode escapes |
| **Non-tty stdout (pipe/file)** | `[EXPT]` `initscr()` still emits escapes and returns a window; `endwin()` raises `ERR` | `[DOC]/[EXPT]` strips control codes, writes plain text | `[EXPT]` writes ~230 bytes of escape sequences to stderr; does not raise. `run(headless=True)` writes nothing |

**SSH.** `[DOC]` OpenSSH requests a pseudo-terminal for an interactive session by
default ("ssh by default will only request a pseudo-terminal (pty) for
interactive sessions when the client has one"); `-T` disables pty allocation and
`-t` forces it. RFC 4254 §6.2 defines the `pty-req` message carrying the `TERM`
value and the character width/height, so a remote TUI receives a tty and a
`TERM`.
(https://man.openbsd.org/ssh.1; https://www.rfc-editor.org/rfc/rfc4254.txt §6.2.)
All three therefore work over SSH provided the session has a pty and a sane
`TERM`. `[INF]`

**`TERM` unset.** `[EXPT]` `curses.setupterm()` raises
`curses.error: setupterm: could not find terminfo database` when `TERM` is
unset or empty, and `curses.error: setupterm: could not find terminal` when
`TERM=unknown`. Rich does not need terminfo and still renders; Textual renders
its TUI regardless.

---

## 3. Headless behavior (the "a UI failure must never stop the assistant" case)

### 3.1 `curses`

- `[DOC]` `curses.setupterm(term=None, fd=-1)`: "Raise a `curses.error` if the
  terminal could not be found or its terminfo database entry could not be
  read." `term=None` uses `$TERM`.
- `[DOC]` `curses.initscr()`: "If there is an error opening the terminal, the
  underlying curses library may cause the interpreter to exit." This is the
  dangerous case: a bad TERM can terminate the process, not merely raise.
- `[EXPT]` `TERM` unset with stdout piped → `curses.initscr()` raised
  `curses.error: setupterm: could not find terminal`.
- `[EXPT]` `TERM=xterm` with stdout piped → `initscr()` did **not** raise; it
  emitted the alternate-screen/reset sequence (`ESC[?1049h … ESC[?1049l`) to
  stdout and returned a window object; the subsequent `endwin()` raised
  `curses.error: endwin() returned ERR`. So an `isatty()` check is not a
  sufficient guard on its own; `curses` will still write escape bytes to a
  redirected stdout.
- `[EXPT]` `TERM=dumb` → `setupterm()` succeeds; `tigetnum("colors")` is `-1`
  and `tigetstr("cup")` / `tigetstr("clear")` are `None`. A curses program can
  start on a dumb terminal but has no cursor addressing, so layout is broken.

`[INF]` Therefore, for `curses` the fallback must be decided *before*
`initscr()`: test `sys.stdout.isatty()`, `TERM` non-empty, `setupterm()`
succeeds, and cursor addressing (`tigetstr("cup")`) is non-None; if any fails,
do not enter curses.

### 3.2 `rich` 15.0.0

- `[DOC]` "If Rich detects that it is not writing to a terminal it will strip
  control codes from the output." "Rich will remove animations such as progress
  bars and status indicators when not writing to a terminal."
- `[DOC]` `TERM` values `"dumb"` or `"unknown"` "will disable color/style and
  some features that require moving the cursor, such as progress bars."
- `[DOC]` Environment overrides: `FORCE_COLOR`, `NO_COLOR` (takes precedence
  over `FORCE_COLOR`), `TTY_COMPATIBLE` (`"1"`/`"0"` override tty detection),
  `TTY_INTERACTIVE`, `COLUMNS`/`LINES`.
- `[DOC]` Upstream source `Console.is_terminal` checks, in order:
  explicit `force_terminal`; IDLE; Jupyter; `TTY_COMPATIBLE`; `FORCE_COLOR`;
  otherwise `file.isatty()`, returning `False` on `ValueError`.
  `is_dumb_terminal` is `is_terminal and TERM.lower() in ("dumb","unknown")`.
  `_detect_color_system()` returns `None` when not a terminal or when the
  terminal is dumb; it reads `COLORTERM` (`truecolor`/`24bit` → truecolor) and
  the `TERM` suffix (`-256color` → 256) to pick a color system.
  (`rich/console.py`, v15.0.0.)
- `[EXPT]` piped stdout: `is_terminal=False`, `color_system=None`, and
  `print("[bold red]hello[/] world")` produced `hello world` with no escape
  bytes. `TERM=dumb` and `TERM` unset behaved the same when stdout was not a
  tty.

`[INF]` Rich degrades to plain, escape-free text when not on a terminal, and
disables color under `TERM=dumb`. This is the safest of the three for the
"never stop the assistant" requirement, because it does not require the UI to
be abandoned — it just renders plainly.

### 3.3 `textual` 8.2.8

- `[DOC]` Upstream `LinuxDriver.__init__` sets its output file to
  `sys.__stderr__` (`linux_driver.py:58`), and `start_application_mode()` writes
  the alternate-screen, mouse, focus, kitty-keyboard and cursor-hide sequences
  (`linux_driver.py:266-292`) with no check that stderr is a tty.
- `[DOC]` `os.isatty(self.fileno)` is used only to decide SIGTTOU/SIGTTIN
  handling (`linux_driver.py:205`), and `sys.__stdin__.isatty()` only to decide
  whether to send the kitty sync-mode query (`linux_driver.py:60`, `:309`).
  Neither gates the main escape output.
- `[DOC]` `Driver._writer_thread.WriterThread.isatty()` "Pretend to be a
  terminal. Returns: True." (`_writer_thread.py:28-33`). `_PrintCapture.isatty()`
  and `_NullFile.isatty()` also return `True` (`app.py:252-266, 281-286`).
- `[EXPT]` `App.run()` with stdout redirected and stderr captured emitted
  ~230 bytes of control sequences to stderr under every `TERM` tried
  (`xterm-256color`, `dumb`, `unknown`, and unset). It did not raise and exited
  `0`. It therefore does **not** auto-degrade on a non-tty.
- `[DOC]/[EXPT]` `App.run(headless=True)` selects `HeadlessDriver`, whose
  `write()` is a no-op and which emits no escapes; `[EXPT]` it wrote nothing.
  Textual also has `run(inline=True)` (added 0.55.0) for apps that sit under the
  prompt instead of taking over the screen; `[DOC]` inline mode is not supported
  on Windows (irrelevant here).
- `[DOC]` Textual is asyncio-based and runs its own event loop (`App.run` /
  `run_async`).

`[INF]` Textual must be told not to take over the terminal. To use it safely
without a tty you would gate on `isatty()` and choose `headless=True` (or not
start it at all); otherwise it writes escape sequences into whatever stderr is
attached to.

**A macOS-specific caveat for Textual `[DOC]`:** the FAQ "Why doesn't Textual
look good on macOS?" states that the default macOS Terminal.app does not render
Textual apps well (misaligned box characters) and "is limited to 256 colors";
it recommends iTerm2, Kitty, or WezTerm. The project targets macOS
(`docs/ui/README.md:41`), so this is a real product concern, not an
implementation detail.

---

## 4. Terminal capability detection — reliable patterns and pitfalls

| Need | Reliable call | Source / note |
| --- | --- | --- |
| Is stdout a tty | `sys.stdout.isatty()`; low-level `os.isatty(fd)` | `[DOC]` `io.IOBase.isatty()`: "Return True if the stream is interactive (i.e., connected to a terminal/tty device)." `os.isatty(fd)`: "Return True if the file descriptor fd is open and connected to a tty(-like) device." |
| Is stdin a tty | `sys.stdin.isatty()` | same; this is the one that matters for a TUI's input |
| Is this a *usable* terminal (terminfo + cursor addressing) | `curses.setupterm()` then `curses.tigetstr("cup") is not None` | `[DOC]` `setupterm` raises `curses.error` on failure; `tigetstr` returns `None` if the capability is absent. `[EXPT]` `TERM=dumb` → `cup=None`; unset → `setupterm` raises. |
| Color depth | after `setupterm()`: `curses.tigetnum("colors")`; plus `COLORTERM` and `TERM` | `[DOC]` `tigetnum` returns `-1` if canceled/absent, `-2` if not a numeric capability. `COLORTERM` is a de-facto emulator convention, not a published standard (`[U]` for a spec); `[DOC]` Rich reads `COLORTERM in ("truecolor","24bit")` and the `TERM` suffix. |
| Terminal size | `shutil.get_terminal_size(fallback=(80, 24))`; lower level `os.get_terminal_size(fd)` | `[DOC]` `shutil.get_terminal_size` checks `COLUMNS`/`LINES` first, then queries `sys.__stdout__` via `os.get_terminal_size()`, then uses `fallback`. Changed in 3.11: fallback is also used when `os.get_terminal_size()` returns zeroes. `os.get_terminal_size` raises `OSError` if not a terminal. |
| Resize | `signal.SIGWINCH` handler; re-query size | `[DOC]` `signal.SIGWINCH` — "Window resize signal", Availability: Unix. Handlers run in the main thread only; signal handlers run in the main thread. `[DOC]` `curses.resizeterm` also updates curses' own SIGWINCH bookkeeping. |

**Pitfalls (`[DOC]`/`[EXPT]`/`[INF]`).**

1. `isatty()` is necessary but **not sufficient**. `[EXPT]` with a real tty
   variable and `TERM` unset, `setupterm()` still raises; and with
   `TERM=xterm` but a *piped* stdout, `initscr()` still wrote escapes. Test the
   terminal, not just the fd.
2. `isatty()` can raise `ValueError` on a closed file — Rich catches this;
   a detector should too. `[DOC]` upstream Rich source.
3. `TERM=dumb` passes `setupterm()` but gives `colors=-1` and no cursor
   addressing; treat "dumb" as "no TUI". `[EXPT]`
4. `COLUMNS`/`LINES` can be stale or wrong for the *current* terminal because
   `shutil.get_terminal_size` prefers them over an ioctl; if the program needs
   the true window size, query `os.get_terminal_size()` first or clear them.
   `[DOC]` shutil description; `[INF]` for the staleness consequence.
5. `SIGWINCH` does not exist on Windows (`[DOC]` Availability: Unix) and handlers
   must be installed on the main thread. Not targeted by this project.
6. `curses` is **not thread-safe** in the default ncurses build: `[DOC]` "the
   screen state is shared and not thread-safe; since the blocking and refresh
   methods ... release the GIL, unsynchronized use from several threads can then
   crash the interpreter. Serialize the calls." This matters because the
   assistant runs an asyncio loop.
7. ncurses < 6.1-20190511 had a resize bug that could segfault; `[DOC]` Python's
   `addstr` note (bpo-35924). Modern ncurses is past the fix, but it is a
   documented historical pitfall.

**Illustrative helper set** (detection only; not an implementation proposal):

```text
tty_out   = sys.stdout.isatty() and sys.stdin.isatty()      # guard ValueError
term      = os.environ.get("TERM", "")
usable    = False
if tty_out and term and term.lower() not in ("dumb", "unknown"):
    try:
        curses.setupterm()
        usable = curses.tigetstr("cup") is not None          # cursor addressing
    except curses.error:
        usable = False
colors    = curses.tigetnum("colors") if usable else 0       # -1/0 => no color
truecolor = os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")
size      = shutil.get_terminal_size(fallback=(80, 24))      # or os.get_terminal_size()
# resize: signal.signal(signal.SIGWINCH, handler) on the main thread (Unix)
```

---

## 5. Integration shape — in-process module vs separate process

**Current facts.**

- The console is an **in-process** bus module: `ConsoleModule` is registered in
  `MODULE_SPECS` and is in `NON_CRITICAL` (`main.py:69-88`). It reads stdin with
  `loop.add_reader(sys.stdin.fileno(), ...)` when stdin is a tty, otherwise a
  non-blocking poll (`console/module.py:122-127`, `:156-168`). Its
  `start()`/`stop()` own the reader and the readline history
  (`console/module.py:40-84`).
- The orb is a **separate process**: `main.py` spawns
  `sys.executable -m aiassistant.orb`, fire-and-forget, stdout/stderr
  `DEVNULL`, bounded restart (3 in 10 minutes), and it "holds no state the
  assistant needs" (`main.py:190-240`; `docs/architecture/modules/orb.md:70-89`).
- The orb's contract explicitly says: "No asyncio loop runs in this process"
  and "The orb process can crash and restart without affecting the assistant"
  (`orb.md:48-49`). It depends only on `bridge/`, never on `agent/`
  (`orb.md:5-9`).
- Display mode is resolved to `orb` or `console`; `auto` = orb when a GUI is
  available, console otherwise; `--mode console` and `AIASSISTANT_DISPLAY_OFF`
  force console (`config.py:112-134`; `main.py:10-22`).

**Analysis.**

- **Terminal ownership.** A full-screen TUI needs exclusive use of stdin/stdout
  (or stderr for Textual). The in-process console already owns stdin via
  `add_reader`. The two cannot both own the terminal in one process. `[INF]`
- **Event loop ownership.** Textual runs its own asyncio event loop
  (`App.run`/`run_async`); curses blocks in `getch()`. Running either inside the
  assistant's bus loop would contend with the console reader and with the
  loop's latency budget (`CLAUDE.md` trap 4: providers block; the loop must keep
  ticking). A separate process sidesteps this entirely. `[INF]`
- **Crash isolation.** The orb's requirement — a UI crash must not affect the
  assistant (REQ-ORB-001, `orb.md:81-89`) — is met by a separate process and
  not by an in-process module. `curses.initscr()` can exit the interpreter on a
  bad terminal (`[DOC]`), which in-process would kill the assistant. `[INF]`
- **State transport already exists.** The `Bridge` WS client already does
  connect/register/subscribe/publish/reconnect with backoff
  (`src/aiassistant/bridge.py`), and a subscribe-only client is supported
  (`docs/contracts/api.md:23-25`). A TUI can reuse it unchanged and be named as
  its own module, as the orb is. `[INF]`
- **Selection, not concurrency.** A TUI is an alternative front-end, not an
  additional one. Whichever of console/TUI is active should own the terminal;
  the natural place to express that is the existing display-mode resolution
  (add a `tui` value), not a new coordination mechanism. `[INF]`

**Conclusion.** The evidence favors the **separate-process shape**, mirroring
the orb: it removes terminal and event-loop contention with the console, gives
crash isolation, and reuses the existing bridge. This is an architectural
recommendation; the decision belongs to `plan`/`architect`. `[INF]`

---

## 6. Existing project facts: what the GUI orb consumes, and the TUI equivalent

### 6.1 How the GUI orb gets its state

`[DOC]` `docs/contracts/protocols.md` IF-0004 (`:239-280`) fixes the orb's
topic surface. Subscribes:

| Topic | Payload | Drives |
| --- | --- | --- |
| `voice.state` | `state` enum | Base state and color |
| `voice.level` | `{level, source, ts}` | Pulse amplitude |
| `agent.delta` | `{kind, text, index}` | Streaming transcript |
| `agent.tool.event` | tool lifecycle | Tool activity rows |
| `agent.final` | final text | Transcript settle |
| `agent.turn.error` | error | Error state |
| `voice.overflow` | `{dropped, queue_cap}` | Warning badge |
| `status.assistant.ready` | `{}` | Window appears |
| `status.harness` | `{harness, model}` | Backend badge |

Publishes: `user.input.text`, `command.agent.interrupt`,
`command.voice.mute` (`protocols.md:270-276`).

`[DOC]` The bridge API (`docs/contracts/api.md:13-39`) is the wire sequence:
open `ws://<bind>:<port>`; send `{"token":…}` first if configured; register
`{"action":"register","module_name":"orb",…}`; subscribe one frame per topic;
then receive `{"topic":…,"payload":…}` forwards. A subscribe-only client is
supported. On reconnect, re-auth/re-register/re-subscribe
(`api.md:100-115`); the resync-request topic is explicitly **undefined**
(`api.md:113-115`).

`[DOC]` `MOD-0008` says the orb "must not ... import `agent/`" and depends only
on `bridge/` (`orb.md:5-9`); it "never derives state the assistant has
published; it displays what it receives" (`orb.md:42-44`).

The topic constants exist in code: `AGENT_DELTA`, `AGENT_TOOL_EVENT`,
`AGENT_FINAL`, `AGENT_TURN_ERROR`, `VOICE_STATE`, `VOICE_LEVEL`,
`VOICE_OVERFLOW`, `USER_INPUT_TEXT`, `COMMAND_AGENT_INTERRUPT`,
`COMMAND_VOICE_MUTE`, `STATUS_ASSISTANT_READY`, `STATUS_HARNESS`
(`src/aiassistant/bus/topics.py:13-44`).

### 6.2 What a TUI equivalent would need

`[INF]` A TUI that mirrors the orb would subscribe to the same IF-0004 topics —
at minimum `voice.state`, `voice.level`, `agent.delta`, `agent.final`,
`agent.turn.error`, `status.assistant.ready`, `status.harness`, with
`agent.tool.event` and `voice.overflow` if it renders activity and warnings —
and publish `user.input.text`, `command.agent.interrupt`, and
`command.voice.mute`. It would reuse `bridge.Bridge` and speak only the bridge
protocol, exactly as the orb does.

### 6.3 Observed gap in the console (relevant context)

`[DOC]` `ConsoleModule.start()` currently subscribes to the **as-built** topic
names `response.text`, `status.ears.listening`, `status.ears.processing`,
`status.ears.transcribed`, `status.ears.error`, `status.mouth.error`,
`status.assistant.ready` (`console/module.py:42-48`) and publishes via
`self.bus.user_input(line)` (`console/module.py:204`). It does **not** subscribe
to `voice.state`, `agent.delta`, or `agent.final`. `[DOC]` IF-0005 marks
`voice.transcribed` as replacing `status.ears.transcribed` and `voice.tts.*` as
replacing `status.mouth.*` (`protocols.md:318-327`). `[INF]` So the console's
event surface is behind the IF-0004/IF-0005 contract that the orb uses; a TUI
built to IF-0004 would be *more* aligned with the documented contract than the
console is today. This is a fact about the current code, not a judgment on it.

---

## Recommendation table

Per the research role, this summarizes what the evidence supports for this
project. The choice itself belongs to `plan`/`architect`.

| Library | Strongest reason **to pick** | Strongest reason **to avoid** |
| --- | --- | --- |
| **`curses`** (stdlib) | Zero pip dependency; available on Linux/macOS distribution Pythons; you own the whole loop and can build exactly the orb-like frame you want with no framework (`pyproject.toml:11-29` adds nothing). | It is an *optional* stdlib extension linked against system ncurses, so it can be absent (a Python built without ncurses headers) and needs a working terminfo/`TERM`; `TERM` unset raises and `initscr()` can exit the interpreter on a bad terminal `[DOC]`; it is not thread-safe `[DOC]`; and you must write window, resize, and input handling by hand. |
| **`rich`** 15.0.0 | Degrades safely: strips control codes when stdout is not a tty and disables color on `TERM=dumb` `[DOC]`, so a rendering problem never becomes a crash; small pure-Python footprint and MIT license; well suited to transcript/status panels rather than a full-screen app. | It is a *rendering* library, not an application framework: no full-screen application mode, no widget/event loop; a true "orb TUI" would still need `Live`/`Screen` assembled by hand. Adds 3 pure-Python distributions (rich, markdown-it-py, pygments + mdurl) `[EXPT]`. |
| **`textual`** 8.2.8 | Purpose-built full-screen TUI: DOM, CSS, widgets, `RichLog`, `Input`, `Sparkline`, asyncio-native — the closest match to an ambient assistant UI with a transcript, composer, and state indicator; MIT license. | On a non-tty it still writes ~230 bytes of escape sequences to `sys.__stderr__` unless you explicitly use `headless=True`/`isatty()` gating `[EXPT]`; heavy footprint (9 distributions measured) `[EXPT]`; and macOS Terminal.app renders it poorly and is limited to 256 colors, per Textual's own FAQ `[DOC]` — a real concern for a macOS-targeted product. |

**Terminal-detection helper set I would rely on.** Test in this order and treat
any failure as "no TUI, fall back to the console":

1. `sys.stdout.isatty()` and `sys.stdin.isatty()` (guarding `ValueError`).
2. `TERM` present and not `dumb`/`unknown`.
3. `curses.setupterm()` succeeds and `curses.tigetstr("cup")` is not `None`
   (the reliable "usable terminal" test).
4. Color depth from `curses.tigetnum("colors")`, with `COLORTERM` and the
   `TERM` suffix as secondary hints.
5. Size from `shutil.get_terminal_size(fallback=(80, 24))` (or
   `os.get_terminal_size()` when the true size is needed), refreshed on
   `signal.SIGWINCH`.

Wrap all of it in `try/except` and never let a detection or UI failure stop the
assistant, matching the existing console-fallback requirement
(REQ-CONSOLE-001, `orb.md:81-83`).

---

## Open / conflicting

- **macOS `curses` on a from-source Python** is `[U]`: the CPython docs
  establish "Unix optional module + libncurses", but I did not read an Apple or
  python.org primary page confirming that a given macOS Python ships `_curses`.
  What would settle it: run `python3 -c "import curses; curses.setupterm()"` on
  each macOS interpreter the project supports (system, python.org, Homebrew),
  or read the python.org macOS installer's build configuration.
- **`COLORTERM`** has no authoritative standard I could read (`[U]`); it is
  widely implemented and is what Rich reads `[DOC]`. What would settle it: the
  terminal emulator's own documentation for each terminal the project supports.
- **Textual's exact behavior on a pty with `TERM=dumb`** — I tested a
  redirected (non-tty) output, not a pty with `TERM=dumb`. `[U]` for the exact
  visual result. What would settle it: run a Textual app under `script`/a pty
  with `TERM=dumb` and capture the output.
- **The resync topic for a reconnecting client** is undefined in the current
  docs (`api.md:113-115`; `[DOC]`). A TUI needing gap recovery inherits this
  open item from the orb.
- **Whether a TUI should replace or coexist with the console** is a product
  decision, not established here. The evidence (one terminal, one owner) points
  to selection via display mode; the decision belongs to `plan`/`product-designer`.
