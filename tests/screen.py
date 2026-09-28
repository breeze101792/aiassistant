"""Render terminal output so a test can assert on what the user sees.

Asserting on raw bytes is misleading for this console: it overwrites a line
with ``\\r`` and erases rows with ``\\x1b[K``/``\\x1b[2K``/``\\x1b[nA``. A byte
count then reports text the terminal never displays, which is exactly how a
wrapped-answer duplication looked "safe" when it was not.

This is a small, correct subset of terminal behaviour: CR and LF, CSI K (erase
in line), CSI J (erase display), CSI A/B (cursor up/down), CSI H, and wrapping.
It is the model the console's own output is written against.
"""

import re

_CSI = re.compile(r"\x1b\[([0-9;?]*)([a-zA-Z@])")
_CHARSET = re.compile(r"\x1b[()][A-Za-z0-9]")


class Screen:
    """A terminal grid that escapes are applied to."""

    def __init__(self, columns: int = 120, rows: int = 500):
        self.columns = columns
        self.grid = [[" "] * columns for _ in range(rows)]
        self.row = 0
        self.col = 0

    def _grow(self):
        while self.row >= len(self.grid):
            self.grid.append([" "] * self.columns)

    def _newline(self):
        self.row += 1
        self.col = 0
        self._grow()

    def feed(self, text: str) -> "Screen":
        i = 0
        while i < len(text):
            char = text[i]
            if char == "\x1b":
                match = _CSI.match(text, i)
                if match:
                    params, command = match.group(1), match.group(2)
                    self._apply(params, command)
                    i = match.end()
                    continue
                skipped = _CHARSET.match(text, i)
                i = skipped.end() if skipped else i + 1
                continue
            if char == "\r":
                self.col = 0
            elif char == "\n":
                self._newline()
            elif char == "\b":
                self.col = max(0, self.col - 1)
            else:
                self._put(char)
            i += 1
        return self

    def _apply(self, params: str, command: str) -> None:
        if command == "A":
            self.row = max(0, self.row - (int(params) if params else 1))
        elif command == "B":
            self.row = min(len(self.grid) - 1, self.row + (int(params) if params else 1))
        elif command == "K":
            # 0/absent: cursor to end of line. 1: start to cursor. 2: whole line.
            if params == "2":
                start, end = 0, self.columns
            elif params == "1":
                start, end = 0, self.col + 1
            else:
                start, end = self.col, self.columns
            for col in range(start, end):
                self.grid[self.row][col] = " "
        elif command == "J":
            if params in ("2", "3"):
                self.grid = [[" "] * self.columns for _ in self.grid]
                self.row = self.col = 0
        elif command == "H":
            self.row = self.col = 0

    def _put(self, char: str) -> None:
        if self.col >= self.columns:
            self._newline()
        self.grid[self.row][self.col] = char
        self.col += 1

    def lines(self) -> list[str]:
        """The displayed rows, right-trimmed, without trailing blank rows."""
        out = ["".join(row).rstrip() for row in self.grid]
        while out and not out[-1]:
            out.pop()
        return out

    def text(self) -> str:
        return "\n".join(self.lines())


def render(text: str, columns: int = 120) -> list[str]:
    """Render escape-laden output and return the displayed lines."""
    return Screen(columns=columns).feed(text).lines()
