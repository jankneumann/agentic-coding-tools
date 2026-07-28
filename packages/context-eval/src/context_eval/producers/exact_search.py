"""The exact-search arms: a fair keyword ranker and the naive phrase floor.

Rescued from ``run_eval.py:86-104`` and changed in exactly three ways, each of
which was a defect there (design D5, D10):

1. **The repository root is injected.** ``run_eval.py:31`` computed
   ``REPO_ROOT = HERE.parents[3]``, which silently resolved to ``<repo>/openspec``
   once the change was archived. Here the root is a constructor parameter with
   no default, validated at construction, and a root that is not a checkout is an
   :class:`ApparatusError`.
2. **A missing search backend is loud.** ``run_eval.py``'s ``_rg`` caught
   ``FileNotFoundError`` and returned ``[]``, so "ripgrep is not installed" and
   "this query matched nothing" produced the same number. Both are
   :class:`ApparatusError` here. An empty ranking remains a legitimate answer;
   it is no longer how the harness reports that it could not look.
3. **The result is rendered under a budget.** ``run_eval.py`` compared a top-5
   *file list* against a top-5 file list, which is fair for hit@k and
   meaningless for utility. Both arms are rendered under the single
   ``ContextBudget`` the corpus manifest declares — the same four bounds ri-12
   applies — so "how much irrelevant material did the agent have to read" is a
   comparison rather than a measurement of whose cap was tighter.

The ranking itself is preserved verbatim: the query is tokenized into words of
three or more letters, stopwords are dropped, files are ranked by the count of
distinct query terms they match, then by total matching lines, then by path.
That last component makes the order total, so no tie can fall through to the
order the search backend happened to emit.

**No threshold appears in this module.** ``k``, ``max_files`` and the rest arrive
as data; ``test_thresholds_are_not_readable_from_the_scoring_modules`` fails if
one is written here as a literal.
"""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..models import Budget
from ..scoring.arms import Arm, RenderedHit, RenderedOmission, fallback_arm

#: Verbatim from ``run_eval.py:34-39``. Preserved rather than improved: the ten
#: rescued cases were measured against this list, and a better one would make
#: the new numbers incomparable with the numbers being carried forward.
STOPWORDS: frozenset[str] = frozenset(
    {
        "how", "are", "is", "the", "a", "an", "does", "do", "it", "in", "to", "of", "for",
        "where", "what", "so", "as", "at", "on", "from", "with", "that", "this", "next",
        "can", "its", "it's", "up", "by", "or", "and", "run", "runs", "running",
        "gets", "get", "pick", "know", "leave", "which", "uses", "use", "two", "same",
    }
)

#: Words of three or more ASCII letters. The bound lives inside the pattern
#: string, where it is documentation rather than an arithmetic constant.
TERM_PATTERN = re.compile(r"[a-zA-Z_]{3,}")

#: The file kinds ``run_eval.py`` ranked. A lexical baseline that ranked binary
#: assets or lockfiles would beat itself on noise.
RANKED_SUFFIXES: tuple[str, ...] = (".py", ".sql", ".ts", ".js", ".sh", ".md")

#: Seconds any single search subprocess may take before the run is an apparatus
#: failure. Not a threshold the gate is judged against — a liveness bound.
SEARCH_TIMEOUT_SECONDS = 120

_MARKER_GIT = ".git"
_MARKER_OPENSPEC = "openspec"

#: The arm names this module produces.
KEYWORD_ARM = "baseline"
PHRASE_ARM = "naive_phrase"

#: What a rendered arm reports when the query has no rankable terms or nothing
#: matched. A fallback is a scored outcome, never an absent measurement.
EMPTY_TRIGGER = "no_context"
EMPTY_REASON = "index_returned_no_hits"


class ApparatusError(RuntimeError):
    """The measurement could not be taken. Never a number, never an empty list."""


def validate_repository_root(repository_root: Path | str) -> Path:
    """Resolve *repository_root* and prove it is a repository checkout.

    ``.git`` is checked with ``exists()`` rather than ``is_dir()`` because a
    linked worktree's ``.git`` is a *file* — and every mutating skill in this
    repository runs inside a managed worktree, so an ``is_dir()`` check would
    reject the only place the harness is ever actually run.
    """
    root = Path(repository_root).resolve()
    if not root.is_dir():
        raise ApparatusError(f"repository root is not a directory: {root}")
    if not (root / _MARKER_GIT).exists():
        raise ApparatusError(
            f"repository root has no {_MARKER_GIT} entry, so it is not a checkout: {root}"
        )
    if not (root / _MARKER_OPENSPEC).is_dir():
        raise ApparatusError(
            f"repository root has no {_MARKER_OPENSPEC}/ directory: {root}"
        )
    return root


def query_terms(query: str) -> tuple[str, ...]:
    """The distinct, sorted content words of *query*.

    Sorted, so accumulation order is a property of the query rather than of a
    set's iteration order. ``run_eval.py`` iterated ``set(terms)`` directly; that
    happened to be harmless because it only fed counters, but it is the exact
    shape design D16 forbids and it costs nothing to remove.
    """
    return tuple(sorted({term for term in TERM_PATTERN.findall(query.lower())} - STOPWORDS))


def is_rankable(file_path: str) -> bool:
    return file_path.endswith(RANKED_SUFFIXES)


class Searcher(Protocol):
    """A lexical search backend over one repository checkout.

    Injected rather than chosen, so the number a report records always names the
    backend that produced it. There is no auto-detection: a harness that quietly
    used a different backend depending on what happened to be installed would
    produce two incomparable baselines under one name.
    """

    def term_matches(self, term: str) -> Mapping[str, tuple[int, ...]]:
        """Repository-relative path -> sorted 1-based lines matching *term*."""

    def phrase_matches(self, phrase: str) -> Mapping[str, tuple[int, ...]]:
        """The same, for a literal case-insensitive phrase."""

    def count_matches(self, term: str) -> Mapping[str, int]:
        """Repository-relative path -> number of matching lines."""


@dataclass(frozen=True)
class RipgrepSearcher:
    """``run_eval.py``'s backend, with its silent-failure reflex removed.

    Invoked with an argument list and a ``--`` terminator, never through a shell
    with the query interpolated — which ``run_eval.py`` also did correctly and
    which is worth keeping explicit, since the query is corpus data.
    """

    repository_root: Path
    executable: str = "rg"
    timeout_seconds: int = SEARCH_TIMEOUT_SECONDS

    def term_matches(self, term: str) -> Mapping[str, tuple[int, ...]]:
        return self._run(["-e", term])

    def phrase_matches(self, phrase: str) -> Mapping[str, tuple[int, ...]]:
        return self._run(["-F", "-e", phrase])

    def count_matches(self, term: str) -> Mapping[str, int]:
        return {path: len(lines) for path, lines in self.term_matches(term).items()}

    def _run(self, pattern_args: Sequence[str]) -> Mapping[str, tuple[int, ...]]:
        command = [
            self.executable,
            "--line-number",
            "--no-heading",
            "--with-filename",
            "--ignore-case",
            *pattern_args,
            "--",
            ".",
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=str(self.repository_root),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as error:
            raise ApparatusError(
                f"the search backend {self.executable!r} is not installed; "
                "an unavailable backend is an apparatus failure, not an empty result"
            ) from error
        except subprocess.TimeoutExpired as error:
            raise ApparatusError(f"{self.executable} timed out: {command!r}") from error
        # 0 = matches, 1 = no matches. Anything else is the tool refusing.
        if completed.returncode not in (0, 1):
            raise ApparatusError(
                f"{self.executable} exited {completed.returncode}: {completed.stderr.strip()}"
            )
        return _group_lines(_parse_grep_lines(completed.stdout))


@dataclass(frozen=True)
class TrackedFileSearcher:
    """A pure-Python backend over the checkout's tracked files.

    Exists for two reasons the ripgrep backend cannot serve. It is hermetic, so
    the algorithm-pinning test needs no external binary and cannot be silently
    skipped in CI; and it enumerates via ``git ls-files``, so "the tree at this
    revision" means the tracked tree rather than whatever ignore rules happened
    to be in force.

    *file_list* overrides enumeration entirely, which is what a fixture tree
    uses. An empty tuple is a legitimate, deliberately empty corpus of files —
    not a failure to enumerate.
    """

    repository_root: Path | None = None
    file_list: tuple[str, ...] | None = None
    timeout_seconds: int = SEARCH_TIMEOUT_SECONDS

    def term_matches(self, term: str) -> Mapping[str, tuple[int, ...]]:
        return self._search(term.lower())

    def phrase_matches(self, phrase: str) -> Mapping[str, tuple[int, ...]]:
        return self._search(phrase.lower())

    def count_matches(self, term: str) -> Mapping[str, int]:
        return {path: len(lines) for path, lines in self.term_matches(term).items()}

    def files(self) -> tuple[str, ...]:
        if self.file_list is not None:
            return tuple(sorted(self.file_list))
        root = self._root()
        try:
            completed = subprocess.run(
                ["git", "ls-files", "-z"],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as error:
            raise ApparatusError(f"could not enumerate tracked files under {root}") from error
        if completed.returncode != 0:
            raise ApparatusError(
                f"git ls-files exited {completed.returncode}: {completed.stderr.strip()}"
            )
        return tuple(sorted(entry for entry in completed.stdout.split("\0") if entry))

    def _root(self) -> Path:
        if self.repository_root is None:
            raise ApparatusError("TrackedFileSearcher needs a repository root to read files")
        return self.repository_root

    def _search(self, needle: str) -> Mapping[str, tuple[int, ...]]:
        tracked = self.files()
        if not tracked:
            return {}
        root = self._root()
        found: dict[str, tuple[int, ...]] = {}
        for relative in tracked:
            path = root / relative
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                # A tracked path that cannot be read is not a match and not a
                # failure: submodules and symlinks both land here.
                continue
            lines = tuple(
                number
                for number, line in enumerate(text.splitlines(), start=1)
                if needle in line.lower()
            )
            if lines:
                found[relative] = lines
        return found


def _parse_grep_lines(stdout: str) -> list[tuple[str, int]]:
    """``./path:12:content`` -> ``("path", 12)``, ignoring anything unparseable."""
    parsed: list[tuple[str, int]] = []
    for raw in stdout.splitlines():
        path, separator, remainder = raw.partition(":")
        if not separator:
            continue
        number, separator, _ = remainder.partition(":")
        if not separator:
            continue
        try:
            line_number = int(number)
        except ValueError:
            continue
        normalized = path[len("./") :] if path.startswith("./") else path
        parsed.append((normalized, line_number))
    return parsed


def _group_lines(pairs: Sequence[tuple[str, int]]) -> Mapping[str, tuple[int, ...]]:
    grouped: dict[str, list[int]] = {}
    for path, line_number in pairs:
        grouped.setdefault(path, []).append(line_number)
    return {path: tuple(sorted(set(lines))) for path, lines in sorted(grouped.items())}


@dataclass(frozen=True)
class RankedFile:
    """One file's position in the keyword ranking, with the numbers behind it."""

    file_path: str
    distinct_terms: int
    total_matches: int
    match_lines: tuple[int, ...]

    @property
    def sort_key(self) -> tuple[int, int, str]:
        """The total order. The path component is what makes ties decidable."""
        return (-self.distinct_terms, -self.total_matches, self.file_path)


@dataclass(frozen=True)
class ExactSearchProducer:
    """Renders both exact-search arms for one query, under one declared budget.

    Every input is injected: the repository root, the budget resolved from the
    corpus manifest, and the search backend. Nothing is discovered.
    """

    repository_root: Path
    budget: Budget
    searcher: Searcher
    _root: Path = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_root", validate_repository_root(self.repository_root))

    # -- ranking ---------------------------------------------------------

    def rank(self, query: str) -> tuple[RankedFile, ...]:
        """The fair keyword ranking over the whole checkout, best first."""
        terms = query_terms(query)
        if not terms:
            return ()

        distinct: Counter[str] = Counter()
        total: Counter[str] = Counter()
        lines: dict[str, set[int]] = {}
        for term in terms:
            for file_path, matched in sorted(self.searcher.term_matches(term).items()):
                if not is_rankable(file_path):
                    continue
                distinct[file_path] += 1
                total[file_path] += len(matched)
                lines.setdefault(file_path, set()).update(matched)

        ranked = [
            RankedFile(
                file_path=file_path,
                distinct_terms=distinct[file_path],
                total_matches=total[file_path],
                match_lines=tuple(sorted(lines[file_path])),
            )
            for file_path in sorted(distinct)
        ]
        return tuple(sorted(ranked, key=lambda entry: entry.sort_key))

    def rank_phrase(self, query: str) -> tuple[RankedFile, ...]:
        """The naive literal-phrase floor: every file containing the query verbatim.

        Ranked by path alone. There is nothing to rank *by* — a literal phrase
        either appears or does not — and path order at least makes the arm
        reproducible.
        """
        matches = self.searcher.phrase_matches(query)
        return tuple(
            RankedFile(
                file_path=file_path,
                distinct_terms=1,
                total_matches=len(matched),
                match_lines=tuple(sorted(matched)),
            )
            for file_path, matched in sorted(matches.items())
            if is_rankable(file_path)
        )

    # -- rendering -------------------------------------------------------

    def render(self, query: str) -> Arm:
        """The fair keyword arm, rendered under the declared budget."""
        return self._render(self.rank(query), KEYWORD_ARM)

    def render_naive_phrase(self, query: str) -> Arm:
        """The literal-phrase arm — recorded as a third column, never gated on."""
        return self._render(self.rank_phrase(query), PHRASE_ARM)

    def _render(self, ranked: Sequence[RankedFile], arm: str) -> Arm:
        candidates = self._candidates(ranked)
        if not candidates:
            return fallback_arm(arm, EMPTY_TRIGGER, EMPTY_REASON)
        kept, omissions = apply_budget(candidates, self.budget)
        if not kept:  # pragma: no cover - every block is <= max_hit_lines by construction
            return fallback_arm(arm, EMPTY_TRIGGER, "all_hits_omitted")
        return Arm(arm=arm, status="injected", hits=kept, omissions=omissions)

    def _candidates(self, ranked: Sequence[RankedFile]) -> tuple[RenderedHit, ...]:
        """Candidate excerpts in round-robin order across the ranked files.

        Round-robin, not file-by-file, and the choice is load-bearing. A grep
        loop's top file often contains a dozen scattered matches; taking them all
        before looking at the second file would let one file consume the whole hit
        budget and would systematically starve the baseline of required-file
        coverage. Since the baseline is the control this evaluation's claim rests
        on, a self-handicapping baseline would flatter the semantic arm exactly
        where the comparison matters. Position within the file breaks first, then
        rank, then line — a total order with no set iteration in it.
        """
        blocks = [self._blocks(entry) for entry in ranked]
        depth = max((len(group) for group in blocks), default=0)
        candidates: list[RenderedHit] = []
        for index in range(depth):
            for group in blocks:
                if index < len(group):
                    candidates.append(group[index])
        return tuple(candidates)

    def _blocks(self, entry: RankedFile) -> tuple[RenderedHit, ...]:
        """One file's matching lines, greedily grouped into per-hit windows.

        A block opens at a matching line and absorbs every later match within
        ``max_hit_lines`` of its start; the block ends at its last absorbed match,
        never at a padded boundary. Tight spans on purpose: ``evidence_density``
        divides by rendered lines, so padding an excerpt to a fixed window would
        quietly penalise the arm for material nobody asked for.
        """
        blocks: list[RenderedHit] = []
        start: int | None = None
        end: int | None = None
        for line in entry.match_lines:
            if start is None or line > start + self.budget.max_hit_lines - 1:
                if start is not None and end is not None:
                    blocks.append(RenderedHit(entry.file_path, start, end))
                start = line
            end = line
        if start is not None and end is not None:
            blocks.append(RenderedHit(entry.file_path, start, end))
        return tuple(blocks)


def apply_budget(
    candidates: Sequence[RenderedHit], budget: Budget
) -> tuple[tuple[RenderedHit, ...], tuple[RenderedOmission, ...]]:
    """First-fit over *candidates*, admitting a hit only if all four bounds hold.

    Reimplemented from ri-12's ``apply_budget`` rather than imported, because
    ``packages/`` must not import ``skills/`` (design D4). The behaviour it
    mirrors precisely is the absence of an early ``break``: the scan continues
    past a rejected hit, so a later small excerpt can still be admitted after a
    large one was skipped. Breaking out would make the section's contents depend
    on where the first oversized hit happened to land in the ranking.
    """
    kept: list[RenderedHit] = []
    omissions: list[RenderedOmission] = []
    files: dict[str, None] = {}
    used_lines = 0

    for hit in candidates:
        lines = hit.line_count
        if len(kept) >= budget.max_hits:
            reason = "hit_count_cap"
        elif hit.file_path not in files and len(files) >= budget.max_files:
            reason = "file_count_cap"
        elif lines > budget.max_hit_lines:
            reason = "hit_line_cap"
        elif used_lines + lines > budget.max_total_lines:
            reason = "total_line_cap"
        else:
            kept.append(hit)
            files[hit.file_path] = None
            used_lines += lines
            continue
        omissions.append(
            RenderedOmission(hit.file_path, hit.start_line, hit.end_line, reason)
        )

    return tuple(kept), tuple(omissions)
