from unittest.mock import Mock


def test_weak_lower_bound_forms_are_flagged() -> None:
    mock = Mock()
    assert mock.call_count >= 1
    assert mock.call_count > 0
    assert 1 <= mock.call_count
    assert 0 < mock.call_count
