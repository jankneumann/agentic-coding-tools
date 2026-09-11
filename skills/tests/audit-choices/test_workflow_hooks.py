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
        assert '/audit-choices "$CHANGE_ID" --run-id "$RUN_ID"' in section
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
