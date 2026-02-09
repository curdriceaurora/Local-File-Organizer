# Audio Organization

![Audio panel](../assets/audio-panel.svg)

Audio support adds metadata extraction and classification for music, podcasts, voice notes, and other audio files.

## Install Audio Dependencies

```bash
pip install -e ".[audio]"
```

Audio features also benefit from a system FFmpeg install.

## Use the Audio View

1. Launch the TUI: `file-organizer tui`.
2. Press `5` for Audio.
3. Use `j`/`k` to change selection, `r` to rescan.

The view shows metadata (duration, codec, bitrate) and classification confidence.
