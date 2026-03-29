#!/usr/bin/env python3
"""Extract session log content from agent conversation history.

Implements a 3-tier extraction strategy:
  Tier 1: Agent session transcript (e.g., Claude Code local storage)
  Tier 2: Handoff document history (coordinator, if available)
  Tier 3: Structured prompts for agent self-summary fallback

Outputs structured markdown matching the session-log.md template.

Exit codes:
  0 — Success (session log generated)
  1 — Error (extraction failed)
  2 — No source available (all tiers exhausted, self-summary prompts printed)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


# --- Tier 1: Claude Code session transcript ---

CLAUDE_SESSION_PATHS = [
    Path.home() / ".claude" / "projects",
    Path.home() / ".claude" / "sessions",
]


def try_extract_claude_transcript(
    change_id: str,
) -> str | None:
    """Attempt to find and parse Claude Code session transcript.

    Searches Claude Code's local storage for sessions related to the change-id.
    Returns structured markdown or None if not found.
    """
    for base_path in CLAUDE_SESSION_PATHS:
        if not base_path.exists():
            continue

        # Look for session files containing the change-id
        try:
            for session_file in sorted(base_path.rglob("*.jsonl"), reverse=True):
                try:
                    content = session_file.read_text(encoding="utf-8")
                    if change_id not in content:
                        continue

                    messages = _parse_jsonl_messages(content)
                    if messages:
                        return _format_transcript_as_session_log(
                            messages, change_id, str(session_file), "transcript"
                        )
                except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
                    continue
        except PermissionError:
            continue

    return None


def _parse_jsonl_messages(content: str) -> list[dict[str, str]]:
    """Parse JSONL transcript into a list of role/content message dicts."""
    messages: list[dict[str, str]] = []
    for line in content.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            role = entry.get("role", "")
            msg_content = entry.get("content", "")
            if isinstance(msg_content, list):
                # Handle structured content blocks
                text_parts = []
                for block in msg_content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        text_parts.append(block)
                msg_content = "\n".join(text_parts)
            if role and msg_content:
                messages.append({"role": role, "content": str(msg_content)})
        except json.JSONDecodeError:
            continue
    return messages


# --- Tier 2: Handoff document compilation ---


def try_extract_from_handoffs(
    change_id: str,
    handoff_source: str | None = None,
) -> str | None:
    """Compile session context from handoff document history.

    Reads handoff documents (JSON files) and constructs a session log
    from the structured summary, decisions, and completed_work fields.
    """
    handoff_docs: list[dict] = []

    if handoff_source:
        source_path = Path(handoff_source)
        if source_path.exists():
            try:
                data = json.loads(source_path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    handoff_docs = data
                elif isinstance(data, dict):
                    handoff_docs = [data]
            except (json.JSONDecodeError, UnicodeDecodeError):
                return None

    if not handoff_docs:
        return None

    # Filter for relevant handoffs
    relevant = [
        h for h in handoff_docs
        if change_id in json.dumps(h)
    ]

    if not relevant:
        return None

    return _format_handoffs_as_session_log(relevant, change_id)


def _format_handoffs_as_session_log(
    handoffs: list[dict], change_id: str,
) -> str:
    """Format handoff documents into session-log.md structure."""
    sections: dict[str, list[str]] = {
        "decisions": [],
        "completed": [],
        "next_steps": [],
    }

    session_ids: list[str] = []
    agent_names: set[str] = set()
    dates: list[str] = []

    for h in handoffs:
        if "decisions" in h and isinstance(h["decisions"], list):
            sections["decisions"].extend(h["decisions"])
        if "completed_work" in h and isinstance(h["completed_work"], list):
            sections["completed"].extend(h["completed_work"])
        if "next_steps" in h and isinstance(h["next_steps"], list):
            sections["next_steps"].extend(h["next_steps"])
        if "session_id" in h and h["session_id"]:
            session_ids.append(str(h["session_id"]))
        if "agent_name" in h and h["agent_name"]:
            agent_names.add(str(h["agent_name"]))
        if "created_at" in h and h["created_at"]:
            dates.append(str(h["created_at"]))

    lines: list[str] = [f"# Session Log: {change_id}", ""]

    # Summary
    lines.append("## Summary")
    lines.append("")
    summary_parts = [h.get("summary", "") for h in handoffs if h.get("summary")]
    lines.append(" ".join(summary_parts) if summary_parts else "Session context compiled from handoff documents.")
    lines.append("")

    # Key Decisions
    lines.append("## Key Decisions")
    lines.append("")
    if sections["decisions"]:
        for i, d in enumerate(sections["decisions"], 1):
            lines.append(f"{i}. {d}")
    else:
        lines.append("No explicit decisions recorded in handoff documents.")
    lines.append("")

    # Alternatives Considered
    lines.append("## Alternatives Considered")
    lines.append("")
    lines.append("Not available from handoff documents — handoffs capture decisions but not alternatives.")
    lines.append("")

    # Trade-offs
    lines.append("## Trade-offs")
    lines.append("")
    lines.append("Not available from handoff documents.")
    lines.append("")

    # Open Questions
    lines.append("## Open Questions")
    lines.append("")
    if sections["next_steps"]:
        for ns in sections["next_steps"]:
            lines.append(f"- [ ] {ns}")
    else:
        lines.append("None recorded.")
    lines.append("")

    # Session Metadata
    lines.append("## Session Metadata")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| Agent Type | {', '.join(sorted(agent_names)) or 'unknown'} |")
    lines.append(f"| Session ID(s) | {', '.join(session_ids) or 'N/A'} |")
    date_range = f"{dates[0]} — {dates[-1]}" if dates else "unknown"
    lines.append(f"| Date Range | {date_range} |")
    lines.append(f"| Interactions | {len(handoffs)} handoff document(s) |")
    lines.append("| Source | handoff-documents |")
    lines.append("")

    return "\n".join(lines)


# --- Tier 3: Self-summary prompt generation ---


def generate_self_summary_prompt(change_id: str) -> str:
    """Generate a structured prompt for agent self-summary.

    When tiers 1 and 2 are unavailable, this prompt guides the agent
    to produce a session log from its current context window.
    """
    return f"""# Session Log Self-Summary Request

Please generate a session log for OpenSpec change `{change_id}` by summarizing
the current conversation. Use the following structure:

## Summary
Write 2-3 sentences summarizing what was discussed and decided.

## Key Decisions
List each significant decision with a brief rationale. Number them.

## Alternatives Considered
For each key decision, list alternatives that were discussed and why
they were rejected. Use a table format (Alternative | Why Rejected).

## Trade-offs
List explicit trade-offs accepted (e.g., "Chose X over Y because...").

## Open Questions
List any unresolved questions as checklist items.

## Session Metadata
Fill in the metadata table with:
- Agent Type: (your agent type)
- Session ID(s): (current session ID if available)
- Date Range: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
- Interactions: (approximate count)
- Source: self-summary

IMPORTANT:
- Do NOT include raw code blocks or full file contents
- Do NOT include any secrets, API keys, tokens, or passwords
- Focus on the reasoning behind decisions, not mechanical steps
- Keep the total under 500 lines
"""


# --- Formatting helpers ---


def _format_transcript_as_session_log(
    messages: list[dict[str, str]],
    change_id: str,
    source_path: str,
    source_type: str,
) -> str:
    """Format parsed transcript messages into session-log.md structure.

    Extracts decisions, trade-offs, and questions from conversation flow.
    """
    lines: list[str] = [f"# Session Log: {change_id}", ""]

    # Extract decision-oriented content from messages
    decisions: list[str] = []
    questions: list[str] = []

    for msg in messages:
        content = msg["content"].lower()
        # Heuristic: messages containing decision language
        if any(kw in content for kw in ["decided", "chose", "decision", "went with", "opted for"]):
            # Take first 200 chars as a decision summary
            summary = msg["content"][:200].replace("\n", " ").strip()
            if summary:
                decisions.append(summary)
        if any(kw in content for kw in ["question", "unclear", "todo", "revisit", "open issue"]):
            summary = msg["content"][:200].replace("\n", " ").strip()
            if summary:
                questions.append(summary)

    lines.append("## Summary")
    lines.append("")
    lines.append(
        f"Session log extracted from agent transcript for change `{change_id}`. "
        f"{len(messages)} messages processed."
    )
    lines.append("")

    lines.append("## Key Decisions")
    lines.append("")
    if decisions:
        for i, d in enumerate(decisions[:20], 1):  # Cap at 20
            lines.append(f"{i}. {d}")
    else:
        lines.append("No explicit decisions detected in transcript. Review manually.")
    lines.append("")

    lines.append("## Alternatives Considered")
    lines.append("")
    lines.append("Extracted from transcript — review for completeness.")
    lines.append("")

    lines.append("## Trade-offs")
    lines.append("")
    lines.append("Extracted from transcript — review for completeness.")
    lines.append("")

    lines.append("## Open Questions")
    lines.append("")
    if questions:
        for q in questions[:10]:
            lines.append(f"- [ ] {q}")
    else:
        lines.append("No open questions detected.")
    lines.append("")

    lines.append("## Session Metadata")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append("| Agent Type | claude |")
    lines.append(f"| Session ID(s) | {Path(source_path).stem} |")
    lines.append(f"| Date Range | {datetime.now(timezone.utc).strftime('%Y-%m-%d')} |")
    lines.append(f"| Interactions | {len(messages)} |")
    lines.append(f"| Source | {source_type} |")
    lines.append("")

    return "\n".join(lines)


# --- Main ---


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract session log from agent conversation history."
    )
    parser.add_argument("--change-id", required=True, help="OpenSpec change-id")
    parser.add_argument(
        "--agent-type", default="claude",
        choices=["claude", "codex", "gemini", "other"],
        help="Agent type for extraction strategy (default: claude)"
    )
    parser.add_argument(
        "--handoff-source",
        help="Path to handoff documents JSON file (for tier 2 extraction)"
    )
    parser.add_argument(
        "--output",
        help="Output file path (default: stdout)"
    )
    parser.add_argument(
        "--prompt-only", action="store_true",
        help="Only output the self-summary prompt (tier 3), skip tiers 1 and 2"
    )
    args = parser.parse_args()

    change_id = args.change_id

    if args.prompt_only:
        prompt = generate_self_summary_prompt(change_id)
        if args.output:
            Path(args.output).write_text(prompt, encoding="utf-8")
        else:
            print(prompt)
        return 0

    # Tier 1: Try agent session transcript
    if args.agent_type == "claude":
        print("Tier 1: Searching for Claude Code session transcript...", file=sys.stderr)
        result = try_extract_claude_transcript(change_id)
        if result:
            print("Tier 1: Session transcript found and extracted.", file=sys.stderr)
            _write_output(result, args.output)
            return 0
        print("Tier 1: No session transcript found.", file=sys.stderr)

    # Tier 2: Try handoff documents
    if args.handoff_source:
        print("Tier 2: Extracting from handoff documents...", file=sys.stderr)
        result = try_extract_from_handoffs(change_id, args.handoff_source)
        if result:
            print("Tier 2: Handoff documents compiled.", file=sys.stderr)
            _write_output(result, args.output)
            return 0
        print("Tier 2: No relevant handoff documents found.", file=sys.stderr)

    # Tier 3: Generate self-summary prompt
    print("Tier 3: Generating self-summary prompt for agent.", file=sys.stderr)
    prompt = generate_self_summary_prompt(change_id)
    if args.output:
        Path(args.output).write_text(prompt, encoding="utf-8")
    else:
        print(prompt)

    return 2


def _write_output(content: str, output_path: str | None) -> None:
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    else:
        print(content)


if __name__ == "__main__":
    sys.exit(main())
