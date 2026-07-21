"""Concurrency contracts for shared history persistence."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from file_organizer.history.models import OperationType, TransactionStatus
from file_organizer.history.tracker import OperationHistory

pytestmark = [pytest.mark.integration, pytest.mark.ci]


def test_shared_history_serializes_transaction_mutations(tmp_path: Path) -> None:
    history = OperationHistory(tmp_path / "history.db")
    source = tmp_path / "source.txt"
    source.write_text("content")

    def record(index: int) -> str:
        transaction_id = history.start_transaction({"worker": index})
        history.log_operation(
            OperationType.COPY,
            source,
            tmp_path / f"destination-{index}.txt",
            transaction_id=transaction_id,
        )
        assert history.commit_transaction(transaction_id)
        return transaction_id

    with ThreadPoolExecutor(max_workers=8) as executor:
        transaction_ids = list(executor.map(record, range(32)))

    assert len(set(transaction_ids)) == 32
    assert history.db.get_operation_count() == 32
    for transaction_id in transaction_ids:
        transaction = history.get_transaction(transaction_id)
        assert transaction is not None
        assert transaction.status == TransactionStatus.COMPLETED
        assert transaction.operation_count == 1
