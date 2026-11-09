"""Fixture loader: a fixture directory is data only (design D5, D6).

Layout: ``scenario.yaml`` (principals, steps, durations, declared status transitions),
``seed/`` (files committed to the seed commit on ``main``) and any directories that steps
name in ``files_from``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from mpsim.errors import UsageError
from mpsim.model import STEP_NAMES, Fixture, PrincipalSpec, Step, Transition
from mpsim.world import MIN_PRINCIPALS

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _transition(raw: Any, where: str) -> Transition | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("set_status"), str):
        raise UsageError(f"{where}: expected a mapping with a string 'set_status'")
    return Transition(raw["set_status"])


def _step(raw: Any, fixture_dir: Path, where: str) -> Step:
    if not isinstance(raw, dict):
        raise UsageError(f"{where}: step must be a mapping")
    name = raw.get("name")
    if name not in STEP_NAMES:
        raise UsageError(f"{where}: step name must be one of {', '.join(STEP_NAMES)}")
    duration = raw.get("duration")
    if not isinstance(duration, int) or isinstance(duration, bool) or duration < 1:
        raise UsageError(f"{where}.{name}: duration must be an integer >= 1")
    files_from = raw.get("files_from")
    if files_from is not None and not (fixture_dir / files_from).is_dir():
        raise UsageError(f"{where}.{name}: files_from {files_from!r} is not a fixture directory")
    return Step(
        name=name,
        duration=duration,
        files_from=files_from,
        on_start=_transition(raw.get("on_start"), f"{where}.{name}.on_start"),
        on_finish=_transition(raw.get("on_finish"), f"{where}.{name}.on_finish"),
    )


def load_fixture(fixture_dir: Path) -> Fixture:
    fixture_dir = Path(fixture_dir)
    descriptor = fixture_dir / "scenario.yaml"
    if not descriptor.is_file():
        raise UsageError("fixture directory has no scenario.yaml")
    data = yaml.safe_load(descriptor.read_text()) or {}
    raw_principals = data.get("principals")
    if not isinstance(raw_principals, list):
        raise UsageError("scenario.yaml: 'principals' must be a list")
    if len(raw_principals) < MIN_PRINCIPALS:
        raise UsageError(
            f"fixture declares {len(raw_principals)} principal(s); "
            f"a scenario needs at least {MIN_PRINCIPALS} principals"
        )
    principals: list[PrincipalSpec] = []
    for index, raw in enumerate(raw_principals):
        where = f"principals[{index}]"
        if not isinstance(raw, dict):
            raise UsageError(f"{where}: must be a mapping")
        name, change_id = raw.get("name"), raw.get("change_id")
        if not isinstance(name, str) or not _NAME_RE.match(name):
            raise UsageError(f"{where}: invalid principal name")
        if not isinstance(change_id, str) or not re.match(r"^sim-[a-z0-9-]+$", change_id):
            raise UsageError(f"{where}: change_id must be a synthetic 'sim-' id")
        steps = tuple(_step(s, fixture_dir, f"{name}") for s in raw.get("steps") or [])
        principals.append(
            PrincipalSpec(name=name, change_id=change_id,
                          roadmap_item=raw.get("roadmap_item"), steps=steps)
        )
    if len({p.name for p in principals}) != len(principals):
        raise UsageError("principal names must be distinct")
    seed_dir = fixture_dir / "seed"
    seed_files = {
        str(p.relative_to(seed_dir)): p.read_text()
        for p in sorted(seed_dir.rglob("*")) if p.is_file()
    } if seed_dir.is_dir() else {}
    return Fixture(fixture_dir, tuple(principals), seed_files)
