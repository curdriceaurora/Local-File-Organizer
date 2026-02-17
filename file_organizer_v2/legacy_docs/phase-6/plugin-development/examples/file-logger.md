# Example: File Logger Plugin

Source: `examples/plugins/file_logger/plugin.py`

Purpose: show a hook callback (`file.organized`) that persists a local artifact.

Gotcha: avoid writing logs to unrestricted paths; use configured directories.
