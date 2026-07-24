"""Domain records for the sample repository."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Greeting:
    recipient: str

    def render(self) -> str:
        return f"Hello, {self.recipient}!"
