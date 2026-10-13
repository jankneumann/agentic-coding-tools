import pytest
from pkg.calc import add, sub


@pytest.fixture
def sample_value():
    return 5


def test_add():
    result = add(1, 2)
    assert result == 3


def test_sub_with_fixtures(tmp_path, sample_value):
    assert sub(sample_value, 2) == 3
