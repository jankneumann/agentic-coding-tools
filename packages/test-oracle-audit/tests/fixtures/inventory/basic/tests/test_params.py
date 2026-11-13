import pytest
from pkg.util import double


@pytest.mark.parametrize("x", [1, 2, 3])
def test_double(x):
    assert double(x) == 2 * x
