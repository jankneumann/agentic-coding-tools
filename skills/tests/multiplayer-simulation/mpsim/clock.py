"""Logical tick clock. It advances only when told to (design D5)."""

from __future__ import annotations


class Clock:
    def __init__(self, start: int = 0) -> None:
        self._tick = start

    @property
    def tick(self) -> int:
        return self._tick

    def advance(self, n: int = 1) -> int:
        if n < 0:
            raise ValueError("a clock cannot run backwards")
        self._tick += n
        return self._tick
