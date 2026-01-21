# History & Undo/Redo Guide

> **Phase 4 Feature** - Complete operation history tracking with undo/redo support for all file operations.

## Overview

The History & Undo/Redo system provides:

1. **Operation History** (#53) - Track all file operations with metadata
2. **Undo/Redo** (#55) - Reverse or replay file operations safely
3. **Transaction Support** - Group operations and undo/redo them together
4. **History Viewer** - Browse and analyze operation history

## Quick Start

### Basic Undo/Redo

```bash

# View recent operations
python -m file_organizer.cli.undo_redo --list

# Undo last operation
python -m file_organizer.cli.undo_redo --undo

# Redo last undone operation
python -m file_organizer.cli.undo_redo --redo

# Preview what would be undone (dry-run)
python -m file_organizer.cli.undo_redo --undo --dry-run

```

### Python API

```python

from file_organizer.history import HistoryTracker, UndoManager
from pathlib import Path

# Track an operation
tracker = HistoryTracker()

# Move a file
source = Path("~/Downloads/file.pdf")
destination = Path("~/Documents/file.pdf")

operation = tracker.track_operation(
    operation_type="move",
    source_path=source,
    destination_path=destination
)

# Later, undo it
undo_manager = UndoManager()
undo_manager.undo_last_operation()

# Or redo it
undo_manager.redo_last_operation()

```

## Operation History

### Tracked Operations

The system tracks all file operations:

**Operation Types:**
- **MOVE**: File moved from one location to another
- **RENAME**: File renamed in same directory
- **DELETE**: File deleted (backed up first)
- **COPY**: File copied to new location
- **CREATE**: New file created

**Tracked Metadata:**
- Timestamp
- Source and destination paths
- File hash (SHA256)
- File size and type
- User context
- Error messages (if failed)

### Using History Tracker

```python

from file_organizer.history import HistoryTracker, OperationType
from pathlib import Path
from datetime import datetime

# Initialize tracker
tracker = HistoryTracker()

# Track a move operation
operation = tracker.track_operation(
    operation_type=OperationType.MOVE,
    source_path=Path("~/Downloads/document.pdf"),
    destination_path=Path("~/Documents/Work/document.pdf"),
    file_hash="abc123...",
    metadata={
        "file_size": 1024000,
        "file_type": "application/pdf",
        "user": "john",
        "reason": "organization"
    }
)

print(f"Tracked operation {operation.id}")

```

### Querying History

```python

from datetime import datetime, timedelta

# Get recent operations
recent = tracker.get_recent_operations(limit=10)

for op in recent:
    print(f"{op.timestamp}: {op.operation_type.value} - {op.source_path.name}")

# Get operations by date range
start = datetime.now() - timedelta(days=7)
end = datetime.now()
weekly = tracker.get_operations_by_date_range(start, end)

print(f"Operations this week: {len(weekly)}")

# Get operations by type
moves = tracker.get_operations_by_type(OperationType.MOVE)
print(f"Total moves: {len(moves)}")

# Get operations by path
docs = tracker.get_operations_by_path(Path("~/Documents"))
print(f"Operations in Documents: {len(docs)}")

```

### History Statistics

```python

# Get operation statistics
stats = tracker.get_statistics()

print(f"Total operations: {stats['total_operations']}")
print(f"By type:")
for op_type, count in stats['by_type'].items():
    print(f"  {op_type}: {count}")

print(f"\nBy status:")
for status, count in stats['by_status'].items():
    print(f"  {status}: {count}")

print(f"\nSuccess rate: {stats['success_rate']:.1%}")

```

## Transactions

### What are Transactions?

Transactions group related operations together so they can be undone/redone as a unit.

**Example Use Cases:**
- Organize entire directory (multiple moves)
- Batch rename files
- Deduplication cleanup (multiple deletes)
- Backup creation (multiple copies)

### Creating Transactions

```python

from file_organizer.history import TransactionManager

# Create transaction manager
tx_manager = TransactionManager()

# Start a transaction
tx_id = tx_manager.begin_transaction(
    description="Organize Downloads folder"
)

try:
    # Perform multiple operations
    for file in files_to_organize:
        operation = tracker.track_operation(
            operation_type=OperationType.MOVE,
            source_path=file,
            destination_path=get_destination(file),
            transaction_id=tx_id
        )

    # Commit transaction
    tx_manager.commit_transaction(tx_id)
    print(f"Transaction {tx_id} committed successfully")

except Exception as e:
    # Rollback on error
    tx_manager.rollback_transaction(tx_id)
    print(f"Transaction {tx_id} rolled back: {e}")

```

### Context Manager for Transactions

```python

# Using context manager (recommended)
with tx_manager.transaction("Batch rename photos") as tx_id:
    for photo in photos:
        new_name = generate_name(photo)
        tracker.track_operation(
            operation_type=OperationType.RENAME,
            source_path=photo,
            destination_path=photo.parent / new_name,
            transaction_id=tx_id
        )
    # Automatically commits on success, rolls back on exception

```

### Querying Transactions

```python

# Get all transactions
transactions = tx_manager.get_transactions()

for tx in transactions:
    print(f"Transaction {tx.id}:")
    print(f"  Description: {tx.description}")
    print(f"  Status: {tx.status.value}")
    print(f"  Operations: {tx.operation_count}")
    print(f"  Created: {tx.created_at}")

# Get specific transaction
tx = tx_manager.get_transaction(tx_id)
operations = tracker.get_operations(transaction_id=tx_id)

print(f"Transaction has {len(operations)} operations")

```

## Undo/Redo Operations

### Basic Undo/Redo

```python

from file_organizer.undo import UndoManager

manager = UndoManager()

# Undo last operation
success = manager.undo_last_operation()

if success:
    print("Operation undone successfully")
else:
    print("Undo failed")

# Redo last undone operation
success = manager.redo_last_operation()

if success:
    print("Operation redone successfully")

```

### Undo Specific Operation

```python

# Undo specific operation by ID
operation_id = 42
can_undo, reason = manager.can_undo(operation_id)

if can_undo:
    success = manager.undo_operation(operation_id)
    print(f"Operation {operation_id} undone")
else:
    print(f"Cannot undo: {reason}")

```

### Undo Entire Transaction

```python

# Undo all operations in a transaction
transaction_id = "tx_20240121_123456"
success = manager.undo_transaction(transaction_id)

if success:
    print(f"Transaction {transaction_id} undone")
    # All operations in the transaction are reversed

```

### Checking Undo/Redo Availability

```python

# Check if operation can be undone
can_undo, reason = manager.can_undo(operation_id)

if not can_undo:
    print(f"Cannot undo: {reason}")
    # Reasons might be:
    # - File no longer exists
    # - Target location doesn't exist
    # - Permission denied
    # - Already undone

# Check if operation can be redone
can_redo, reason = manager.can_redo(operation_id)

if not can_redo:
    print(f"Cannot redo: {reason}")

```

### Undo/Redo Stack

```python

# Get undo stack (operations that can be undone)
undo_stack = manager.get_undo_stack()

print(f"Can undo {len(undo_stack)} operations:")
for op in undo_stack[:5]:  # Show first 5
    print(f"  {op.id}: {op.operation_type.value} - {op.source_path.name}")

# Get redo stack (operations that can be redone)
redo_stack = manager.get_redo_stack()

print(f"\nCan redo {len(redo_stack)} operations:")
for op in redo_stack[:5]:
    print(f"  {op.id}: {op.operation_type.value} - {op.source_path.name}")

```

## CLI Commands

### List Operations

```bash

# List recent operations
python -m file_organizer.cli.undo_redo --list

# List with more details
python -m file_organizer.cli.undo_redo --list --verbose

# List specific number of operations
python -m file_organizer.cli.undo_redo --list --limit 20

# Filter by type
python -m file_organizer.cli.undo_redo --list --type move

# Filter by date
python -m file_organizer.cli.undo_redo --list --since "2024-01-20"

```

### Undo Operations

```bash

# Undo last operation
python -m file_organizer.cli.undo_redo --undo

# Undo specific operation
python -m file_organizer.cli.undo_redo --undo --operation-id 42

# Undo transaction
python -m file_organizer.cli.undo_redo --undo --transaction-id tx_123

# Preview undo (dry-run)
python -m file_organizer.cli.undo_redo --undo --dry-run

# Verbose output
python -m file_organizer.cli.undo_redo --undo --verbose

```

### Redo Operations

```bash

# Redo last undone operation
python -m file_organizer.cli.undo_redo --redo

# Redo specific operation
python -m file_organizer.cli.undo_redo --redo --operation-id 42

# Preview redo
python -m file_organizer.cli.undo_redo --redo --dry-run

```

### View Transaction Details

```bash

# Show transaction details
python -m file_organizer.cli.undo_redo --show-transaction tx_123

# List all transactions
python -m file_organizer.cli.undo_redo --list-transactions

# Show transaction statistics
python -m file_organizer.cli.undo_redo --transaction-stats

```

### Export/Import History

```bash

# Export history to JSON
python -m file_organizer.cli.undo_redo --export history.json

# Export specific date range
python -m file_organizer.cli.undo_redo --export history.json \
    --since "2024-01-01" --until "2024-01-31"

# Import history
python -m file_organizer.cli.undo_redo --import history.json

# Import with merge
python -m file_organizer.cli.undo_redo --import history.json --merge

```

### Cleanup

```bash

# Clean old history (older than 90 days)
python -m file_organizer.cli.undo_redo --cleanup --days 90

# Clean specific transaction
python -m file_organizer.cli.undo_redo --cleanup-transaction tx_123

# Vacuum database (reclaim space)
python -m file_organizer.cli.undo_redo --vacuum

```

## History Viewer

### Interactive Viewer

```python

from file_organizer.undo import HistoryViewer

viewer = HistoryViewer()

# Show recent operations with interactive menu
viewer.show_interactive(limit=20)

# User can:
# - Browse operations
# - Filter by type/date
# - View operation details
# - Undo/redo operations
# - View transaction details

```

### Visual History

```python

# Show timeline view
viewer.show_timeline(
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 1, 31),
    group_by="day"  # or "hour", "week"
)

# Show operation tree (grouped by transaction)
viewer.show_operation_tree(transaction_id="tx_123")

# Show statistics dashboard
viewer.show_statistics()

```

## Safety Features

### Backup Before Undo

Operations that delete or overwrite files create backups:

```python

# Backups stored in:
# ~/.file_organizer/backups/{date}/{operation_id}/

# Backup structure:
backups/
├── 2024-01-21/
│   ├── op_42/
│   │   ├── file.pdf
│   │   └── metadata.json
│   └── op_43/
│       └── document.txt

```

### Dry Run Mode

Preview undo/redo without actually executing:

```python

# Dry run for safety
manager = UndoManager(dry_run=True)

# This will only simulate the undo
success = manager.undo_operation(operation_id)
print("Preview: operation would be undone")

```

### Validation

Before undo/redo, the system validates:
- File still exists at expected location
- Target location is available
- Sufficient permissions
- No conflicts with existing files

```python

# Validate before undo
validation = manager.validate_undo(operation_id)

if not validation.is_valid:
    print(f"Cannot undo: {validation.reason}")
    print("Issues found:")
    for issue in validation.issues:
        print(f"  - {issue}")

```

## Database Storage

### Schema

Operations are stored in SQLite database:

```sql

-- operations table
CREATE TABLE operations (
    id INTEGER PRIMARY KEY,
    operation_type TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    source_path TEXT NOT NULL,
    destination_path TEXT,
    file_hash TEXT,
    metadata JSON,
    transaction_id TEXT,
    status TEXT NOT NULL,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- transactions table
CREATE TABLE transactions (
    id TEXT PRIMARY KEY,
    description TEXT,
    status TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    completed_at DATETIME,
    operation_count INTEGER DEFAULT 0
);

```

### Database Location

Default: `~/.file_organizer/history/operations.db`

### Maintenance

```python

from file_organizer.history import HistoryDatabase

db = HistoryDatabase()

# Optimize database
db.optimize()

# Vacuum (reclaim space)
db.vacuum()

# Get database statistics
stats = db.get_stats()
print(f"Database size: {stats['size_mb']:.2f} MB")
print(f"Total records: {stats['record_count']}")

# Archive old records
db.archive_old_records(
    cutoff_date=datetime.now() - timedelta(days=365),
    archive_path="archive.db"
)

```

## Integration Examples

### With File Organizer

```python

from file_organizer.core import FileOrganizer
from file_organizer.history import HistoryTracker

# Initialize with history tracking
tracker = HistoryTracker()
organizer = FileOrganizer(history_tracker=tracker)

# Organize with history
results = organizer.organize_directory(
    source=Path("~/Downloads"),
    destination=Path("~/Documents"),
    track_history=True  # Enable history tracking
)

# All operations are tracked
print(f"Tracked {len(results.operations)} operations")

# Can undo entire organization
tx_id = results.transaction_id
undo_manager = UndoManager()
undo_manager.undo_transaction(tx_id)

```

### With Deduplication

```python

from file_organizer.services.deduplication import HashDeduplicator
from file_organizer.history import TransactionManager

# Deduplicate with history
deduper = HashDeduplicator()
tx_manager = TransactionManager()

with tx_manager.transaction("Deduplication cleanup") as tx_id:
    duplicates = deduper.find_duplicates(Path("~/Documents"))

    for group in duplicates:
        # Keep first, delete rest
        to_delete = group[1:]
        for file_path in to_delete:
            tracker.track_operation(
                operation_type=OperationType.DELETE,
                source_path=file_path,
                transaction_id=tx_id
            )
            file_path.unlink()

# Can undo entire deduplication if needed
undo_manager.undo_transaction(tx_id)

```

## Best Practices

### 1. Always Use Dry Run First

```bash

# Preview before actual undo
python -m file_organizer.cli.undo_redo --undo --dry-run

```

### 2. Use Transactions for Batch Operations

```python

# Group related operations
with tx_manager.transaction("Batch operation") as tx_id:
    for item in items:
        # Track each operation
        pass

```

### 3. Regular Backups

```bash

# Export history weekly
python -m file_organizer.cli.undo_redo --export weekly-backup.json

```

### 4. Clean Old History

```bash

# Keep database size manageable
python -m file_organizer.cli.undo_redo --cleanup --days 90

```

### 5. Validate Before Undo

```python

# Check if undo is possible
can_undo, reason = manager.can_undo(operation_id)
if can_undo:
    manager.undo_operation(operation_id)

```

## Troubleshooting

### Cannot Undo Operation

**Problem**: Undo fails with "Cannot undo" error

**Common Causes**:
1. File no longer at expected location
2. Target location doesn't exist
3. Permission denied
4. Disk space issues

**Solutions**:

```python

# Check validation details
validation = manager.validate_undo(operation_id)
print(f"Issues: {validation.issues}")

# Manual intervention may be needed

```

### Database Corruption

**Problem**: Database errors or corruption

**Solutions**:

```bash

# 1. Try to repair
python -m file_organizer.cli.undo_redo --repair-db

# 2. Restore from backup
python -m file_organizer.cli.undo_redo --restore-backup backup.db

# 3. Export and reimport
python -m file_organizer.cli.undo_redo --export export.json
# (fix database)
python -m file_organizer.cli.undo_redo --import export.json

```

### Large Database Size

**Problem**: Database grows too large

**Solutions**:

```bash

# Clean old records
python -m file_organizer.cli.undo_redo --cleanup --days 90

# Vacuum database
python -m file_organizer.cli.undo_redo --vacuum

# Archive old records
python -m file_organizer.cli.undo_redo --archive --days 365

```

### Redo Stack Cleared

**Problem**: Cannot redo after new operation

**Explanation**:
- Redo stack is cleared when new operations occur
- This is standard undo/redo behavior
- Export history if you need to preserve it

## Performance Tips

### 1. Batch Operations

```python

# Use transactions for better performance
with tx_manager.transaction() as tx_id:
    for op in operations:
        tracker.track_operation(..., transaction_id=tx_id)

```

### 2. Optimize Queries

```python

# Use indexes for common queries
db.create_index("idx_timestamp", "timestamp")
db.create_index("idx_transaction", "transaction_id")

```

### 3. Regular Maintenance

```bash

# Optimize database monthly
python -m file_organizer.cli.undo_redo --optimize

```

## API Reference

### HistoryTracker

```python

class HistoryTracker:
    def track_operation(
        self,
        operation_type: OperationType,
        source_path: Path,
        destination_path: Optional[Path] = None,
        file_hash: Optional[str] = None,
        metadata: Optional[Dict] = None,
        transaction_id: Optional[str] = None,
    ) -> Operation:
        """Track a file operation."""

    def get_recent_operations(self, limit: int = 10) -> List[Operation]:
        """Get recent operations."""

    def get_operations_by_date_range(
        self,
        start: datetime,
        end: datetime,
    ) -> List[Operation]:
        """Get operations in date range."""

```

### UndoManager

```python

class UndoManager:
    def undo_last_operation(self) -> bool:
        """Undo the last operation."""

    def undo_operation(self, operation_id: int) -> bool:
        """Undo specific operation."""

    def undo_transaction(self, transaction_id: str) -> bool:
        """Undo all operations in transaction."""

    def redo_last_operation(self) -> bool:
        """Redo the last undone operation."""

    def can_undo(self, operation_id: int) -> Tuple[bool, str]:
        """Check if operation can be undone."""

```

### TransactionManager

```python

class TransactionManager:
    def begin_transaction(self, description: str = "") -> str:
        """Start a new transaction."""

    def commit_transaction(self, transaction_id: str) -> bool:
        """Commit transaction."""

    def rollback_transaction(self, transaction_id: str) -> bool:
        """Rollback transaction."""

    @contextmanager
    def transaction(self, description: str = "") -> str:
        """Context manager for transactions."""

```

## Related Documentation

- [Smart Features](./smart-features.md) - Learn from history
- [Analytics](./analytics.md) - Analyze operation patterns
- [Deduplication](./deduplication.md) - Undo deduplication
