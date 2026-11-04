from pkg import util


class TestUtil:
    def test_double_in_class(self):
        assert util.double(2) == 4
