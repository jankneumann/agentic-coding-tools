"""Calculator tests."""

import pytest

from src.calc import add, scale


@pytest.fixture
def sample_pair():
    return (2, 3)


def test_add_matches_spec(sample_pair):
    """Spec: specs/calc/spec.md -- Requirement: Addition, Scenario: Adding two integers."""
    a, b = sample_pair
    assert add(a, b) == 5


def test_scale_snapshot():
    assert scale([1, 2, 3], 2) == [2, 4, 6]
