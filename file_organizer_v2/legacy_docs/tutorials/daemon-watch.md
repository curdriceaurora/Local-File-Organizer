# Daemon Watch + Process

The daemon can watch for new files or run a one-shot pipeline.

## Start the Daemon (Foreground)

```bash
file-organizer daemon start --watch-dir ./inbox --output-dir ./organized --foreground --dry-run
```

## Start the Daemon (Background)

```bash
file-organizer daemon start --watch-dir ./inbox --output-dir ./organized
```

## Watch Events Without Organizing

```bash
file-organizer daemon watch ./inbox
```

## One-Shot Processing

```bash
file-organizer daemon process ./inbox ./organized --dry-run
```

## Stop the Daemon

```bash
file-organizer daemon stop
```

## Status

```bash
file-organizer daemon status
```
