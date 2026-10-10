"""Errors raised by the driver."""


class UsageError(Exception):
    """A semantic usage error. The CLI maps it to exit code 64 (EX_USAGE)."""


class ScenarioError(Exception):
    """The scenario could not be established. The CLI maps it to exit code 1."""
