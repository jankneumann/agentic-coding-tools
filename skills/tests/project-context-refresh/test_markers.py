"""Marker-engine tests (task 2.1): balancing, prose preservation, idempotence."""

from __future__ import annotations

import pytest

import markers


PROSE = """# Title

Hand-authored intro that must never change.

<!-- GENERATED: begin block-a -->
old generated line
<!-- GENERATED: end block-a -->

Closing prose with intent.
"""


def test_find_blocks_returns_ordered_ids():
    text = (
        "<!-- GENERATED: begin one -->\nx\n<!-- GENERATED: end one -->\n"
        "<!-- GENERATED: begin two -->\ny\n<!-- GENERATED: end two -->\n"
    )
    assert markers.block_ids(text) == ("one", "two")


def test_render_preserves_bytes_outside_markers():
    out = markers.render(PROSE, {"block-a": "new generated content"})
    assert "Hand-authored intro that must never change." in out
    assert "Closing prose with intent." in out
    assert "new generated content" in out
    assert "old generated line" not in out
    # Everything before the begin marker and after the end marker is identical.
    assert out.startswith("# Title\n\nHand-authored intro that must never change.\n")
    assert out.endswith("Closing prose with intent.\n")


def test_render_is_idempotent():
    once = markers.render(PROSE, {"block-a": "stable"})
    twice = markers.render(once, {"block-a": "stable"})
    assert once == twice


def test_empty_body_removes_inner_lines_only():
    out = markers.render(PROSE, {"block-a": ""})
    assert "<!-- GENERATED: begin block-a -->\n<!-- GENERATED: end block-a -->" in out
    assert "Hand-authored intro" in out


@pytest.mark.parametrize(
    "bad",
    [
        "<!-- GENERATED: begin x -->\nbody\n",  # unclosed
        "body\n<!-- GENERATED: end x -->\n",  # end with no begin
        "<!-- GENERATED: begin x -->\n<!-- GENERATED: begin y -->\n"
        "<!-- GENERATED: end y -->\n<!-- GENERATED: end x -->\n",  # nested
        "<!-- GENERATED: begin x -->\na\n<!-- GENERATED: end x -->\n"
        "<!-- GENERATED: begin x -->\nb\n<!-- GENERATED: end x -->\n",  # duplicate id
        "<!-- GENERATED: begin x -->\n<!-- GENERATED: end y -->\n",  # mismatched id
    ],
)
def test_malformed_markers_fail_closed(bad):
    with pytest.raises(markers.MarkerError):
        markers.find_blocks(bad)


def test_render_unknown_block_fails_closed():
    with pytest.raises(markers.MarkerError):
        markers.render(PROSE, {"no-such-block": "x"})
