"""Fixture module whose test functions get labelled (never collected: fixtures/ is excluded)."""



def test_y():
    # A new comment explaining the expectation.
    result   =   compute( 2,
                          3 )      # trailing comment


    assert result == 5   # another comment


class TestGroup:

    def test_method(self):
        # reformatted, same logic
        values = [ compute(1, 1),
                   compute(2, 2) ]
        assert values == [ 2,
                           4 ]


def compute(a, b):
    return a + b
