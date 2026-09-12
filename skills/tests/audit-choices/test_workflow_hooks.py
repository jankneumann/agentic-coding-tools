"""Content-pin tests for the three workflow hooks that wire audit-choices
into the lifecycle: iterate-on-implementation Step 11.5, validate-feature
Steps 11/12 + After Validation, and cleanup-feature Step 5.5. Design F1,
F2, F4, F6, F8. Task 3.7.

In the style of skills/tests/cleanup-feature/test_skill_md.py: these are
markdown content assertions, not behavioral tests — the hooks themselves
are SKILL.md prose/bash an agent executes, and a future rewrite could
silently drop a requirement while still "looking right". Each assertion
below exists because design.md names the specific rewrite it guards
against.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parents[2]
ITERATE_SKILL = SKILLS_ROOT / "iterate-on-implementation" / "SKILL.md"
VALIDATE_SKILL = SKILLS_ROOT / "validate-feature" / "SKILL.md"
CLEANUP_SKILL = SKILLS_ROOT / "cleanup-feature" / "SKILL.md"
AUDIT_CHOICES_SKILL = SKILLS_ROOT / "audit-choices" / "SKILL.md"

_FENCE = re.compile(r"```(?:bash|python)?\n(.*?)\n```", re.DOTALL)

READER_PREFIX = "<skill-base-dir>/../audit-choices/scripts/"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _real_headings(text: str) -> list[tuple[int, int, str]]:
    """``(start_offset, level, title)`` for every heading, skipping fenced
    code blocks. Several of the illustrative report/summary templates in
    these skills contain lines like ``## Phase Results`` *inside* a fenced
    example — a naive line-anchored heading regex would treat those as real
    document structure and truncate a section at the fence's own example
    heading."""
    out: list[tuple[int, int, str]] = []
    fence = False
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("```"):
            fence = not fence
        elif not fence:
            m = re.match(r"^(#{2,4})\s+(.*?)\s*$", line)
            if m:
                out.append((offset, len(m.group(1)), m.group(2)))
        offset += len(line)
    return out


def _section(path: Path, needle: str, *, exact: bool = False) -> str:
    """Return the text of the first heading whose title contains ``needle``.

    The section runs from its own heading to the next heading at the same or
    a shallower level, so an assertion scoped to a section cannot be
    satisfied by prose that lives somewhere else in the file.
    """
    text = _text(path)
    headings = _real_headings(text)
    for index, (start, level, title) in enumerate(headings):
        title_lower = title.lower()
        matched = title_lower == needle.lower() if exact else needle.lower() in title_lower
        if not matched:
            continue
        for follow_start, follow_level, _ in headings[index + 1 :]:
            if follow_level <= level:
                return text[start:follow_start]
        return text[start:]
    raise AssertionError(f"{path}: no heading found containing {needle!r}")


def _fences(section_text: str) -> str:
    """Concatenated content of every fenced code block in a section."""
    return "\n".join(_FENCE.findall(section_text))


def _assert_reader_invoked_skill_relative(fence: str, *, label: str) -> None:
    """Every `needs_user.py` mention in a fenced block must be the tail of
    the full skill-relative path — never a bare command and never a
    repo-root `skills/audit-choices/...` path, neither of which resolves
    inside the `.claude/skills/`/`.agents/skills/` runtime mirrors."""
    matches = list(re.finditer(r"needs_user\.py", fence))
    assert matches, f"{label}: no needs_user.py invocation found"
    for m in matches:
        start = m.start()
        window = fence[max(0, start - len(READER_PREFIX)) : start]
        assert window == READER_PREFIX, (
            f"{label}: non-skill-relative needs_user.py invocation near "
            f"{fence[max(0, start - 60): start + 20]!r}"
        )



def _commit_failure_branch(work: str) -> str:
    """The `git commit ... || { ... }` statement from Step 11.5's work fence,
    verbatim.

    Extracted rather than restated so the test exercises the shipped text; a
    rewrite that drops the unstage-and-discard cleanup fails here."""
    start = work.index("git commit -q -m")
    brace = work.index("{", start)
    depth, i = 0, brace
    while i < len(work):
        if work[i] == "{":
            depth += 1
        elif work[i] == "}":
            depth -= 1
            if depth == 0:
                return work[start:i + 1]
        i += 1
    raise AssertionError("commit-failure branch not found in Step 11.5 work fence")

def _choices_row_snippet(fence: str) -> str:
    """The Choices-row snippet from validate-feature Step 11, anchored on
    whichever variable actually starts it — `VALIDATION_ROOT=` (finding 1,
    impl-round-2 fix) or, pre-fix, `CHOICES_JSON=` directly — so a test using
    this helper demonstrates the real pre-fix behavior (resolving through
    `$OPENSPEC_PATH`/`$PROJECT_ROOT`) rather than merely failing to find a
    marker that doesn't exist yet."""
    candidates = [i for i in (fence.find('VALIDATION_ROOT="'), fence.find('CHOICES_JSON="')) if i != -1]
    assert candidates, "could not locate the Choices-row snippet"
    return fence[min(candidates):]


# ─────────────────────────────────────────────────────────────────────────
# iterate-on-implementation Step 11.5
# ─────────────────────────────────────────────────────────────────────────


class TestIterateOnImplementationStep11_5:
    def test_heading_exists_and_mentions_audit_choices(self):
        text = _text(ITERATE_SKILL)
        assert re.search(r"^###\s+11\.5\.", text, re.MULTILINE), "no ### 11.5. heading"
        section = _section(ITERATE_SKILL, "11.5")
        assert "audit-choices" in section.lower()

    def test_not_gated_by_vendor_review(self):
        section = _section(ITERATE_SKILL, "11.5")
        assert re.search(r"not gated by `?VENDOR_REVIEW`?", section, re.I)
        assert "skipped Step 11" in section

    def test_single_skip_line_form(self):
        section = _section(ITERATE_SKILL, "11.5")
        assert "audit-choices: skipped (" in section
        assert "continuing to summary" in section

    def test_executable_block_is_self_contained(self):
        """Every fence in Step 11.5 runs in its own shell process, and the
        agent-performed dispatch sits between two of them. A block that read
        `$JSON_PATH` or `$MD_PATH` from an earlier fence would see them empty,
        `[ -s "" ]` would be false for both, and the step would report
        `audit produced no ledger` on every successful audit — the same
        silent-total-failure shape as running `/audit-choices` from a shell.
        So the block that does the work must define its own paths."""
        section = _section(ITERATE_SKILL, "11.5")
        work = next(f for f in _FENCE.findall(section) if "audit_choices_step()" in f)

        for var in ("CHANGE_DIR", "JSON_PATH", "MD_PATH", "SKIP_REASON"):
            assigned = re.search(rf"^{var}=", work, re.M)
            assert assigned, (
                f"${var} is read by the Step 11.5 work block but never assigned "
                "in it; shell state does not survive between fences."
            )
            first_use = work.index(f"${var}") if f"${var}" in work else len(work)
            assert assigned.start() < first_use, (
                f"${var} is used before it is assigned in the Step 11.5 work block."
            )

    def test_run_id_is_handed_over_explicitly(self):
        """The run id is minted in one fence and used by the agent dispatch in
        the next step, so the skill must say how it crosses that boundary
        rather than relying on an inherited variable."""
        section = _section(ITERATE_SKILL, "11.5")
        assert "shell state does not survive" in section.lower()
        assert re.search(r"--run-id <the run id", section)

    def test_unavailable_cases_have_distinct_skip_reasons(self):
        """Finding 3 (impl-round-2): F6 names two different "unavailable"
        causes — the skill directory (or its runtime mirror) being absent,
        and the harness exposing no sub-agent dispatch tool. A single
        `SKIP_REASON="audit-choices not installed"` covering both means the
        required single warning (scenario skill-workflow.8: "log a single
        warning naming the reason") is false for the second cause. Each
        cause must set its own, distinct reason string."""
        section = _section(ITERATE_SKILL, "11.5")
        assert 'SKIP_REASON="audit-choices not installed"' in section
        assert 'SKIP_REASON="no sub-agent dispatch tool"' in section

    def test_dispatch_is_not_a_bash_command(self):
        """Finding 1 (impl-round-1): `/audit-choices` is an agent slash
        command, not a shell executable. A shell that tries to run it fails
        with exit 127 on every single run, and the warn-and-continue guard
        silently converts that into a false "skipped" success — the audit
        would never run on any invocation while every run reported success.
        The dispatch must therefore be stated as a numbered agent
        instruction *outside* any fenced bash/python block; only the
        bookkeeping (presence checks, comparison, staging, commit, restore)
        may live inside a fence."""
        section = _section(ITERATE_SKILL, "11.5")
        fence = _fences(section)
        assert "/audit-choices" not in fence, (
            "the /audit-choices dispatch must not appear inside a bash fence "
            f"in Step 11.5; found it in: {fence!r}"
        )
        # The dispatch instruction must still exist somewhere in the section
        # (as agent-facing prose), and must name the run-id argument.
        assert re.search(r"/audit-choices <change-id> --run-id <the run id", section)
        # Bookkeeping in the fence must not branch on a captured exit status
        # of the dispatch itself (the old `if ! audit_output=$(...)` shape).
        assert "audit_output" not in fence

    def test_both_files_present_check(self):
        section = _section(ITERATE_SKILL, "11.5")
        fence = _fences(section)
        assert '[ -s "$JSON_PATH" ]' in fence
        assert '[ -s "$MD_PATH" ]' in fence

    def test_git_add_stages_both_paths_under_change_dir_never_bare(self):
        section = _section(ITERATE_SKILL, "11.5")
        fence = _fences(section)
        match = re.search(r"git add\s+((?:\"[^\"]+\"[\s\\]*)+)", fence)
        assert match, "no `git add` invocation found in Step 11.5"
        paths = re.findall(r'"([^"]+)"', match.group(1))
        assert len(paths) == 2, f"expected exactly two pathspecs, got {paths}"
        for p in paths:
            assert p.startswith("openspec/changes/$CHANGE_ID/"), p

    def test_states_f2_commit_rule(self):
        section = _section(ITERATE_SKILL, "11.5")
        assert re.search(r"`entries`\s+array", section)
        assert "header.schema_version" in section
        assert re.search(r"committed revision", section, re.I)
        assert re.search(r"restor\w* the (committed )?pair", section, re.I)
        assert re.search(r"commit\w* nothing", section, re.I)

    def test_f2_comparison_behavior_unchanged_changed_new(self, tmp_path):
        """Finding 7 (impl-round-1): test_states_f2_commit_rule only asserts
        comment strings, so a rewrite that compared the whole document (or
        subtracted only generated_at/run_id) would keep those strings green
        while never actually skipping a commit — header.git_sha and
        audited_range move on every run and would make every re-audit look
        "changed". Following test_orphan_cleanup_behavior's pattern: extract
        the real comparison Python from the fence and execute it against
        real git fixtures. header.git_sha moving between the committed and
        fresh revisions must NOT by itself flip the verdict."""
        section = _section(ITERATE_SKILL, "11.5")
        fence = _fences(section)
        match = re.search(
            r"compare=\$\(python3 - \"\$JSON_PATH\" <<'PYEOF'\n(.*?)\nPYEOF", fence, re.DOTALL
        )
        assert match, "could not locate the F2 comparison python snippet in Step 11.5"
        compare_py = match.group(1)
        assert "entries" in compare_py and "schema_version" in compare_py

        script_path = tmp_path / "compare.py"
        script_path.write_text(compare_py)

        def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
            )

        def run_compare(repo: Path) -> str:
            result = subprocess.run(
                ["python3", str(script_path), "choices.json"],
                cwd=repo,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stderr
            return result.stdout.strip()

        entries_a = [{"stable_id": "a" * 40, "choice": "x", "verdict": "sound"}]
        entries_b = [{"stable_id": "b" * 40, "choice": "y", "verdict": "sound"}]

        def doc(entries: list[dict], *, git_sha: str, schema_version: int = 1) -> str:
            return json.dumps(
                {
                    "header": {
                        "schema_version": schema_version,
                        "git_sha": git_sha,
                        "generated_at": "irrelevant",
                        "run_id": "irrelevant",
                    },
                    "audited_range": {"base_sha": "irrelevant", "head_sha": git_sha},
                    "entries": entries,
                }
            )

        # Case 1: unchanged entries and schema_version, but header.git_sha
        # and audited_range moved (every run's git_sha differs) — must
        # report "unchanged". A whole-header (or subtractive-only) compare
        # would wrongly call this "changed".
        repo_unchanged = tmp_path / "unchanged"
        repo_unchanged.mkdir()
        git(repo_unchanged, "init", "-q")
        git(repo_unchanged, "config", "user.email", "a@b.c")
        git(repo_unchanged, "config", "user.name", "Test")
        (repo_unchanged / "choices.json").write_text(doc(entries_a, git_sha="c" * 40))
        git(repo_unchanged, "add", ".")
        git(repo_unchanged, "commit", "-q", "-m", "prior")
        (repo_unchanged / "choices.json").write_text(doc(entries_a, git_sha="d" * 40))
        assert run_compare(repo_unchanged) == "unchanged"

        # Case 2: entries actually differ — must report "changed".
        repo_changed = tmp_path / "changed"
        repo_changed.mkdir()
        git(repo_changed, "init", "-q")
        git(repo_changed, "config", "user.email", "a@b.c")
        git(repo_changed, "config", "user.name", "Test")
        (repo_changed / "choices.json").write_text(doc(entries_a, git_sha="c" * 40))
        git(repo_changed, "add", ".")
        git(repo_changed, "commit", "-q", "-m", "prior")
        (repo_changed / "choices.json").write_text(doc(entries_b, git_sha="d" * 40))
        assert run_compare(repo_changed) == "changed"

        # Case 3: no committed revision at all (first audit) — must report
        # "new".
        repo_new = tmp_path / "new"
        repo_new.mkdir()
        git(repo_new, "init", "-q")
        git(repo_new, "config", "user.email", "a@b.c")
        git(repo_new, "config", "user.name", "Test")
        (repo_new / "placeholder").write_text("x")
        git(repo_new, "add", "placeholder")
        git(repo_new, "commit", "-q", "-m", "init, no choices.json yet")
        (repo_new / "choices.json").write_text(doc(entries_a, git_sha="c" * 40))
        assert run_compare(repo_new) == "new"

    def test_orphan_cleanup_names_tracked_and_untracked_cases(self):
        section = _section(ITERATE_SKILL, "11.5")
        assert "git checkout --" in section
        assert "rm -f" in section

    def test_orphan_cleanup_branches_per_path_on_ls_files(self):
        """F6: the orphan cleanup must decide *per path*, via `git ls-files
        --error-unmatch`, whether to `git checkout --` (tracked) or `rm -f`
        (untracked) — never run both commands unconditionally against both
        paths, which would delete a tracked file the checkout just
        restored. See test_orphan_cleanup_behavior below for the executable
        proof."""
        fence = _fences(_section(ITERATE_SKILL, "11.5"))
        assert "git ls-files --error-unmatch" in fence
        # The checkout and the rm -f must be in different branches of the
        # same conditional, not two unconditional statements back to back.
        assert re.search(
            r"if git ls-files --error-unmatch .*?\n\s*git checkout --.*?\n\s*else\n\s*rm -f",
            fence,
            re.DOTALL,
        ), "checkout and rm -f must be if/else branches, not sequential commands"

    def test_commit_failure_leaves_no_staged_ledger(self, tmp_path):
        """A commit can fail after `git add` succeeded — a rejecting
        commit-msg hook, a signing failure. The step must not print its
        benign skip line while leaving the pair staged, or a later workflow
        step carries the skipped audit's output into someone else's commit.
        Executes the real `new|changed` branch against a repo whose
        commit-msg hook always rejects."""
        section = _section(ITERATE_SKILL, "11.5")
        work = next(f for f in _FENCE.findall(section) if "audit_choices_step()" in f)
        assert "git reset" in _commit_failure_branch(work), (
            "the commit-failure branch must unstage the ledger pair; "
            "without it `git add` output survives a failed commit"
        )

        repo = tmp_path / "repo"
        change_dir = repo / "openspec" / "changes" / "my-change"
        change_dir.mkdir(parents=True)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
        (repo / "seed").write_text("seed\n")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True)

        hooks = repo / ".git" / "hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        hook = hooks / "commit-msg"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)

        (change_dir / "choices.json").write_text('{"entries": []}')
        (change_dir / "choices.md").write_text("# Choices\n")

        script = (
            'CHANGE_ID="my-change"\n'
            'JSON_PATH="openspec/changes/$CHANGE_ID/choices.json"\n'
            'MD_PATH="openspec/changes/$CHANGE_ID/choices.md"\n'
            'SKIP_REASON=""\n'
            'git add "$JSON_PATH" "$MD_PATH"\n'
            + _commit_failure_branch(work)
            + '\necho "reason=$SKIP_REASON"\n'
        )
        out = subprocess.run(
            ["bash", "-c", script], cwd=repo, capture_output=True, text=True
        )
        assert "reason=git commit failed" in out.stdout, out.stdout + out.stderr

        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=repo, capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert staged == "", f"ledger left staged after a failed commit: {staged!r}"

    def test_orphan_cleanup_behavior(self, tmp_path):
        """Executable proof for F6: run the *actual* orphan-cleanup snippet
        extracted from Step 11.5 against a real git repo, for both the
        first-audit (fully untracked) and post-first-audit (fully tracked,
        truncated write) partial-pair shapes. A prior version of this hook
        ran `git checkout -- $JSON_PATH $MD_PATH` unconditionally and then
        `rm -f` unconditionally, which silently deleted a tracked pair the
        checkout had just restored — this test would have caught that."""
        section = _section(ITERATE_SKILL, "11.5")
        fence = _fences(section)
        match = re.search(
            r'if \[ "\$json_ok" != "\$md_ok" \]; then\n(.*?)\n  fi',
            fence,
            re.DOTALL,
        )
        assert match, "could not locate the partial-pair cleanup block in Step 11.5"
        cleanup_snippet = match.group(1)
        assert "for f in" in cleanup_snippet, "extraction missed the per-path loop"

        script = (
            "run_cleanup_under_test() {\n"
            'JSON_PATH="choices.json"\n'
            'MD_PATH="choices.md"\n'
            + cleanup_snippet
            + "\n}\nrun_cleanup_under_test\n"
        )

        def run_cleanup(repo: Path) -> None:
            result = subprocess.run(
                ["bash", "-c", script], cwd=repo, capture_output=True, text=True
            )
            assert result.returncode == 0, result.stderr

        def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
            )

        # Case 1: first audit ever — both paths untracked.
        repo1 = tmp_path / "untracked"
        repo1.mkdir()
        git(repo1, "init", "-q")
        (repo1 / "choices.json").write_text('{"entries": []}\n')
        # choices.md deliberately absent: interrupted before rendering.
        run_cleanup(repo1)
        assert not (repo1 / "choices.json").exists()
        assert not (repo1 / "choices.md").exists()

        # Case 2: a prior audit already committed a full pair; this run
        # truncated choices.json mid-write before touching choices.md.
        repo2 = tmp_path / "tracked"
        repo2.mkdir()
        git(repo2, "init", "-q")
        git(repo2, "config", "user.email", "a@b.c")
        git(repo2, "config", "user.name", "Test")
        (repo2 / "choices.json").write_text('{"entries": [], "committed": true}\n')
        (repo2 / "choices.md").write_text("# Choices Ledger\n\ncommitted\n")
        git(repo2, "add", ".")
        git(repo2, "commit", "-q", "-m", "chore(choices): prior audit")
        committed_json = (repo2 / "choices.json").read_text()
        committed_md = (repo2 / "choices.md").read_text()

        (repo2 / "choices.json").write_text("")  # truncated mid-write
        run_cleanup(repo2)

        assert (repo2 / "choices.json").exists(), (
            "a tracked file must be restored by `git checkout --`, not deleted"
        )
        assert (repo2 / "choices.json").read_text() == committed_json
        assert (repo2 / "choices.md").read_text() == committed_md
        status = git(repo2, "status", "--porcelain").stdout
        assert status == "", f"working tree must be clean after restore, got: {status!r}"

    def test_step_12_summary_gains_choices_audit_line(self):
        section = _section(ITERATE_SKILL, "12. Present Summary")
        assert "Choices audit:" in section

    def test_dispatch_failed_branch_still_discards_orphan(self, tmp_path):
        """Finding 6 (impl-round-1, antigravity): the dispatch-failed/
        unavailable/WARNING branch returned before the partial-pair block,
        so if the driver wrote or truncated choices.json before failing,
        the orphan stayed on disk. Run the actual `audit_choices_step`
        early-return branch (SKIP_REASON pre-set, as the agent-performed
        dispatch above would do on failure) against a repo where a
        previous audit is committed and the driver has since truncated
        choices.json mid-write, and confirm the orphan is discarded and
        the original SKIP_REASON is preserved."""
        section = _section(ITERATE_SKILL, "11.5")
        fence = _fences(section)
        match = re.search(
            r'  if \[ -n "\$SKIP_REASON" \]; then\n(.*?)\n  fi\n\n  # Verify',
            fence,
            re.DOTALL,
        )
        assert match, "could not locate the early-return orphan-discard block in Step 11.5"
        early_return_block = match.group(1)
        assert "for f in" in early_return_block, "extraction missed the per-path loop"

        def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
            )

        repo = tmp_path / "dispatch-failed"
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "a@b.c")
        git(repo, "config", "user.name", "Test")
        (repo / "choices.json").write_text('{"entries": [], "committed": true}\n')
        (repo / "choices.md").write_text("# Choices Ledger\n\ncommitted\n")
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "chore(choices): prior audit")
        committed_json = (repo / "choices.json").read_text()
        committed_md = (repo / "choices.md").read_text()

        # The driver started writing but the dispatch failed mid-run,
        # truncating choices.json before the agent-performed dispatch step
        # set SKIP_REASON="audit dispatch failed".
        (repo / "choices.json").write_text("")

        script = (
            "run_early_return_under_test() {\n"
            'JSON_PATH="choices.json"\n'
            'MD_PATH="choices.md"\n'
            'SKIP_REASON="audit dispatch failed"\n'
            + early_return_block
            + "\n}\nrun_early_return_under_test\n"
            'echo "SKIP_REASON:$SKIP_REASON"\n'
        )
        result = subprocess.run(["bash", "-c", script], cwd=repo, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr

        # The original failure reason survives the cleanup.
        assert "SKIP_REASON:audit dispatch failed" in result.stdout
        # The orphan is discarded: the tracked pair is restored, not left
        # truncated or partially staged.
        assert (repo / "choices.json").read_text() == committed_json
        assert (repo / "choices.md").read_text() == committed_md
        status = git(repo, "status", "--porcelain").stdout
        assert status == "", f"working tree must be clean after restore, got: {status!r}"

    def _extract_case_block(self) -> str:
        fence = _fences(_section(ITERATE_SKILL, "11.5"))
        match = re.search(r'case "\$compare" in\n(.*?)\n  esac', fence, re.DOTALL)
        assert match, "could not locate the compare-result case block in Step 11.5"
        return 'case "$compare" in\n' + match.group(1) + "\n  esac"

    def test_git_commands_in_case_block_are_guarded(self):
        """Finding 4 (impl-round-1): Step 11.5's prose promises every branch
        warns and continues, but `git add`, `git commit`, and the
        unchanged-path `git checkout --` were unguarded. Without `set -e`
        the step could fall through with no SKIP_REASON and no warning
        (looking like a silent success); with `set -e` it could abort the
        workflow. Content-pin: every git invocation in the compare-result
        case block must be followed by an `||` failure handler."""
        case_block = self._extract_case_block()
        git_lines = [
            line for line in case_block.splitlines() if re.match(r"\s*git (add|commit|checkout)\b", line)
        ]
        assert len(git_lines) >= 3, f"expected git add/commit/checkout, found: {git_lines}"
        for i, line in enumerate(git_lines):
            # The guard may be on the same line (`git foo ... || { ... }`) or
            # a continuation line (`git foo \` then `  || { ... }` next).
            window = case_block[case_block.index(line) : case_block.index(line) + 200]
            assert "||" in window, f"unguarded git command: {line!r}"

    def test_git_commit_failure_sets_skip_reason_not_silent(self, tmp_path):
        """Executable proof: run the real `new|changed` case block against a
        repo where `git commit` fails (nothing to commit, because the
        working-tree files are already byte-identical to HEAD) and assert
        SKIP_REASON is set rather than the block falling through silently."""
        case_block = self._extract_case_block()

        def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
            )

        repo = tmp_path / "commit-fails"
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "a@b.c")
        git(repo, "config", "user.name", "Test")
        change_dir = repo / "openspec" / "changes" / "my-change"
        change_dir.mkdir(parents=True)
        (change_dir / "choices.json").write_text('{"entries": []}\n')
        (change_dir / "choices.md").write_text("# Choices Ledger\n")
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "chore(choices): prior audit")

        script = (
            "run_case_under_test() {\n"
            'compare="changed"\n'
            'CHANGE_ID="my-change"\n'
            'SKIP_REASON=""\n'
            + case_block
            + "\n}\nrun_case_under_test\n"
            'echo "SKIP_REASON:$SKIP_REASON"\n'
        )
        result = subprocess.run(["bash", "-c", script], cwd=repo, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert "SKIP_REASON:git commit failed" in result.stdout, (
            f"a failing git commit must set SKIP_REASON, got stdout={result.stdout!r} "
            f"stderr={result.stderr!r}"
        )

    def test_git_checkout_restore_failure_sets_skip_reason_not_silent(self, tmp_path):
        """Same proof for the `unchanged` branch's `git checkout --`: point
        it at paths git has never heard of, so the checkout fails, and
        assert SKIP_REASON is set instead of the branch silently succeeding."""
        case_block = self._extract_case_block()

        def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
            )

        repo = tmp_path / "checkout-fails"
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "a@b.c")
        git(repo, "config", "user.name", "Test")
        (repo / "README.md").write_text("placeholder\n")
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "init")

        script = (
            "run_case_under_test() {\n"
            'compare="unchanged"\n'
            'JSON_PATH="never-committed.json"\n'
            'MD_PATH="never-committed.md"\n'
            'SKIP_REASON=""\n'
            + case_block
            + "\n}\nrun_case_under_test\n"
            'echo "SKIP_REASON:$SKIP_REASON"\n'
        )
        result = subprocess.run(["bash", "-c", script], cwd=repo, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert "SKIP_REASON:restore of unchanged pair failed" in result.stdout, (
            f"a failing git checkout -- must set SKIP_REASON, got stdout={result.stdout!r} "
            f"stderr={result.stderr!r}"
        )

    def test_stale_half_detected_via_generated_at_mismatch(self, tmp_path):
        """Finding 2 (impl-round-1): the partial-pair guard only tested
        non-emptiness (`[ -s "$JSON_PATH" ]` / `[ -s "$MD_PATH" ]`).
        `write_ledger_pair` writes choices.json then renders choices.md as a
        second, separate operation, so an interruption between them leaves a
        *fresh* choices.json sitting beside the *previous* run's
        choices.md — both non-empty, both checks pass, and a byte-blind
        comparison would call it "changed" and commit a mismatched pair.
        This runs the actual Step 11.5 snippet (the non-emptiness check,
        the new generated_at consistency check, and the partial-pair
        cleanup) against a real git repo with exactly that shape, and
        proves it discards the stale half instead of committing it."""
        section = _section(ITERATE_SKILL, "11.5")
        fence = _fences(section)
        match = re.search(
            r"  local json_ok=false md_ok=false\n(.*?)\n  fi\n\n  # F2:",
            fence,
            re.DOTALL,
        )
        assert match, "could not locate the partial-pair detection block in Step 11.5"
        snippet = "local json_ok=false md_ok=false\n" + match.group(1) + "\n  fi"
        assert "generated_at" in snippet, "extraction missed the staleness check"

        script = (
            "run_check_under_test() {\n"
            'JSON_PATH="choices.json"\n'
            'MD_PATH="choices.md"\n'
            'SKIP_REASON=""\n'
            + snippet
            + "\n}\nrun_check_under_test\n"
            'echo "SKIP_REASON:$SKIP_REASON"\n'
        )

        def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
            )

        repo = tmp_path / "stale"
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "a@b.c")
        git(repo, "config", "user.name", "Test")

        committed_json = '{"header": {"generated_at": "2026-09-01T00:00:00Z"}, "entries": []}\n'
        committed_md = "# Choices Ledger\n\n**Generated**: 2026-09-01T00:00:00Z\n"
        (repo / "choices.json").write_text(committed_json)
        (repo / "choices.md").write_text(committed_md)
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "chore(choices): prior audit")

        # Simulate an interruption: choices.json rewritten by a fresh run,
        # choices.md left as the stale previous render. Both are non-empty.
        (repo / "choices.json").write_text(
            '{"header": {"generated_at": "2026-09-11T00:00:00Z"}, "entries": []}\n'
        )

        result = subprocess.run(["bash", "-c", script], cwd=repo, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr

        assert "SKIP_REASON:partial ledger pair discarded" in result.stdout, (
            f"expected the stale half to be discarded, got stdout={result.stdout!r} "
            f"stderr={result.stderr!r}"
        )
        # Both paths were tracked, so the cleanup must restore (not delete)
        # them, and the working tree must end up clean — the fresh,
        # mismatched choices.json must NOT survive.
        assert (repo / "choices.json").read_text() == committed_json
        assert (repo / "choices.md").read_text() == committed_md
        status = git(repo, "status", "--porcelain").stdout
        assert status == "", f"working tree must be clean after restore, got: {status!r}"


# ─────────────────────────────────────────────────────────────────────────
# validate-feature Steps 11/12 + After Validation
# ─────────────────────────────────────────────────────────────────────────


class TestValidateFeatureChoicesRow:
    def test_choices_row_in_step_11_report_sketch(self):
        section = _section(VALIDATE_SKILL, "11. Validation Report")
        report_fence = _FENCE.findall(section)[0]
        assert "Choices:" in report_fence

    def test_choices_row_in_step_12_report_file_heredoc(self):
        section = _section(VALIDATE_SKILL, "12. Persist Report")
        assert "$CHOICES_ROW" in section

    def test_choices_lines_in_step_12_report_file_heredoc(self):
        """Finding 8 (impl-round-1): the sibling test above only asserted
        `$CHOICES_ROW`, so a regression dropping `$CHOICES_LINES` from the
        heredoc — losing the needs-user entry lines from the persisted
        validation-report.md while the summary row itself still looked
        fine — would have passed."""
        section = _section(VALIDATE_SKILL, "12. Persist Report")
        assert "$CHOICES_LINES" in section

    def test_no_ledger_and_zero_needs_user_forms_are_present_and_distinct(self):
        text = _text(VALIDATE_SKILL)
        assert "○ Choices: no ledger" in text
        assert "✓ Choices: 0 needs-user" in text
        assert "○ Choices: no ledger" != "✓ Choices: 0 needs-user"

    def test_no_choices_markdown_heading(self):
        text = _text(VALIDATE_SKILL)
        assert not re.search(r"^#{1,6}\s+Choices\b", text, re.MULTILINE), (
            "a `## Choices` (or similar) heading would be invisible to "
            "gate_logic.py's allow-list today but picked up by a future edit"
        )

    def test_after_validation_echoes_warning_form(self):
        section = _section(VALIDATE_SKILL, "After Validation", exact=True)
        assert "⚠ Choices:" in section

    def test_choices_row_never_changes_result(self):
        section = _section(VALIDATE_SKILL, "11. Validation Report")
        assert re.search(r"never change[s]? `?Result`?", section, re.I)

    def test_reader_invoked_skill_relative(self):
        section = _section(VALIDATE_SKILL, "11. Validation Report")
        fence = _fences(section)
        _assert_reader_invoked_skill_relative(fence, label="validate-feature")

    def test_choices_lines_initialized_before_branch(self):
        """Finding 5 (impl-round-1): CHOICES_LINES is assigned only in the
        ledger-present branch, and Step 12's heredoc expands it
        unconditionally. Under `set -u` a no-ledger run dies with
        `CHOICES_LINES: unbound variable` while writing
        validation-report.md — the exact path that should print
        `○ Choices: no ledger` and continue. It must be initialized before
        the `if`."""
        section = _section(VALIDATE_SKILL, "11. Validation Report")
        fence = _fences(section)
        match = re.search(r'CHOICES_JSON="[^"]+"\n(.*?)\nif \[ ! -f "\$CHOICES_JSON" \]', fence)
        assert match, "could not locate the CHOICES_JSON/CHOICES_LINES setup"
        assert 'CHOICES_LINES=""' in match.group(1), (
            "CHOICES_LINES must be initialized before the ledger-presence "
            "branch, not only inside the ledger-present `else`"
        )

    def test_no_ledger_path_survives_set_u(self, tmp_path):
        """Executable proof: run the real Choices-row snippet from Step 11
        under `set -u`, in the no-ledger case, and confirm it does not abort
        with `unbound variable` — i.e. CHOICES_LINES is always defined by
        the time Step 12's heredoc (`$CHOICES_ROW` / `$CHOICES_LINES`)
        expands it.

        The snippet resolves the ledger via `git rev-parse --show-toplevel`
        (finding 1, impl-round-2), not `$OPENSPEC_PATH`/`$PROJECT_ROOT`, so
        this runs inside a real (empty) git repo rather than an arbitrary
        `tmp_path` that git would refuse to root."""
        section = _section(VALIDATE_SKILL, "11. Validation Report")
        fence = _fences(section)
        snippet = _choices_row_snippet(fence)
        assert snippet.rstrip().endswith("fi"), f"unexpected snippet tail: {snippet[-40:]!r}"

        repo = tmp_path / "worktree"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

        script = (
            "set -u\n"
            'CHANGE_ID="my-change"\n'
            + snippet
            + '\n# Step 12 use, unquoted like the real heredoc expansion:\n'
            "echo \"row=$CHOICES_ROW lines=$CHOICES_LINES\"\n"
        )
        result = subprocess.run(["bash", "-c", script], cwd=repo, capture_output=True, text=True)
        assert result.returncode == 0, (
            f"no-ledger path must survive `set -u`, got rc={result.returncode} "
            f"stderr={result.stderr!r}"
        )
        assert "unbound variable" not in result.stderr
        assert "row=○ Choices: no ledger" in result.stdout

    def test_choices_fence_does_not_resolve_via_main_checkout_vars(self):
        """Finding 1 (impl-round-2): `worktree.py detect`'s `cmd_detect`
        prints `OPENSPEC_PATH=$main_git/openspec` (and `MAIN_REPO=$main_git`)
        whenever `IN_WORKTREE=true`, and Step 1 sets
        `PROJECT_ROOT="${MAIN_REPO:-...}"` — all three can name the shared
        *main* checkout, not the feature worktree under validation. The
        ledger is committed only to the worktree-relative
        `openspec/changes/$CHANGE_ID/` (iterate-on-implementation Step
        11.5), so the presence check and the reader's `--repo-root` must
        never resolve through `$OPENSPEC_PATH`, `$PROJECT_ROOT`, or
        `$MAIN_REPO`."""
        section = _section(VALIDATE_SKILL, "11. Validation Report")
        fence = _fences(section)
        full_snippet = _choices_row_snippet(fence)
        snippet = full_snippet[: full_snippet.index("\nfi") + len("\nfi")]
        for forbidden in ("$OPENSPEC_PATH", "$PROJECT_ROOT", "$MAIN_REPO"):
            assert forbidden not in snippet, (
                f"Choices fence must not resolve the ledger through {forbidden}: "
                f"{snippet!r}"
            )

    def test_worktree_shaped_env_still_finds_the_ledger(self, tmp_path):
        """Executable proof for finding 1 (impl-round-2): with
        `$OPENSPEC_PATH` and `$PROJECT_ROOT` set worktree-style, pointing at
        a *different* checkout (the main repo, per `worktree.py detect`'s
        convention), and the ledger committed only under the current
        worktree's own `openspec/` tree, the Choices row must still find it
        and render the `⚠` needs-user form — not silently fall back to
        `○ Choices: no ledger`, which is what
        `test_no_ledger_path_survives_set_u` alone could not catch."""
        section = _section(VALIDATE_SKILL, "11. Validation Report")
        fence = _fences(section)
        snippet = _choices_row_snippet(fence).replace(
            "<skill-base-dir>", str(VALIDATE_SKILL.parent)
        )
        assert snippet.rstrip().endswith("fi")

        main = tmp_path / "main"
        (main / "openspec").mkdir(parents=True)  # main checkout: no ledger here

        worktree = tmp_path / "worktree"
        worktree.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=worktree, check=True)
        change_dir = worktree / "openspec" / "changes" / "my-change"
        change_dir.mkdir(parents=True)
        ledger = {
            "entries": [
                {
                    "stable_id": "abc123def456",
                    "confidence": "low",
                    "verdict": "needs-user",
                    "choice": "Chose per-request retry budget of 3",
                }
            ]
        }
        (change_dir / "choices.json").write_text(json.dumps(ledger))

        script = (
            'CHANGE_ID="my-change"\n'
            f'OPENSPEC_PATH="{main}/openspec"\n'
            f'PROJECT_ROOT="{main}"\n'
            f'MAIN_REPO="{main}"\n'
            + snippet
            + '\necho "row=$CHOICES_ROW"\n'
            'echo "lines=$CHOICES_LINES"\n'
        )
        result = subprocess.run(
            ["bash", "-c", script], cwd=worktree, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
        assert "row=⚠ Choices: 1 needs-user entries (choices.md)" in result.stdout, (
            f"expected the ledger under the worktree to be found despite "
            f"main-checkout-shaped OPENSPEC_PATH/PROJECT_ROOT, got: {result.stdout!r}"
        )
        assert "abc123def456" in result.stdout


# ─────────────────────────────────────────────────────────────────────────
# cleanup-feature Step 5.5
# ─────────────────────────────────────────────────────────────────────────


class TestCleanupFeatureStep5_5:
    def test_heading_exists_and_calls_needs_user_py(self):
        text = _text(CLEANUP_SKILL)
        assert re.search(r"^###\s+5\.5\.", text, re.MULTILINE), "no ### 5.5. heading"
        section = _section(CLEANUP_SKILL, "5.5")
        assert "needs_user.py" in section

    def test_states_no_new_gate(self):
        section = _section(CLEANUP_SKILL, "5.5")
        assert re.search(r"no new gate", section, re.I)

    def test_both_empty_case_wordings_present(self):
        section = _section(CLEANUP_SKILL, "5.5")
        assert "no choices ledger" in section
        assert "no open choices" in section

    def test_step_5a_early_exit_points_to_5_5_not_6(self):
        section = _section(CLEANUP_SKILL, "5a. Detect open tasks")
        assert "skip to Step 5.5" in section
        assert "skip to Step 6" not in section

    def test_reader_invoked_skill_relative(self):
        section = _section(CLEANUP_SKILL, "5.5")
        fence = _fences(section)
        _assert_reader_invoked_skill_relative(fence, label="cleanup-feature")


# ─────────────────────────────────────────────────────────────────────────
# audit-choices SKILL.md — --run-id and the range-argument resolution rule
# ─────────────────────────────────────────────────────────────────────────


class TestAuditChoicesArguments:
    def test_run_id_documented(self):
        section = _section(AUDIT_CHOICES_SKILL, "Arguments", exact=True)
        assert "--run-id" in section

    def test_range_form_and_resolution_rule_documented(self):
        args_section = _section(AUDIT_CHOICES_SKILL, "Arguments", exact=True)
        assert "<base-sha>..<head-sha>" in args_section

        steps_section = _section(AUDIT_CHOICES_SKILL, "Steps", exact=True)
        assert re.search(r"explicit range argument.*use it as given", steps_section, re.I)
