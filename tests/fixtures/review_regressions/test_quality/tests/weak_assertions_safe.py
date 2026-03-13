from unittest.mock import Mock


def test_strong_assertions_are_not_flagged() -> None:
    mock = Mock()
    assert mock.call_count == 2
    assert mock.call_count >= True


def test_non_mock_counter_is_not_flagged() -> None:
    call_count = 0
    assert call_count >= 1
