from unittest.mock import Mock


def helper() -> None:
    mock = Mock()
    assert mock.call_count >= 1
