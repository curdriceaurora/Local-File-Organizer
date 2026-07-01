# File Management (Web UI)

This page documents the implemented **Files** surface at `/ui/files`.

## File browser layout

- Left panel: directory tree for allowed roots
- Main panel: file/folder results
- Breadcrumbs: quick navigation inside the selected path

## Implemented filters and sorting

The current Files view supports:

- search by name
- type filter (`image`, `pdf`, `video`, `audio`, `text`, `all`)
- sorting by `name`, `modified`, `created`, `size`, `type`
- ascending/descending sort order
- grid/list view toggle
- incremental loading via **Load more**

## Upload behavior

Uploads are handled by `/ui/files/upload` and enforce validation:

- empty filenames are rejected
- unsafe/invalid names are normalized/rejected
- hidden filenames are rejected by default in this flow
- oversized files are rejected
- existing files are not silently overwritten

After upload, the file results panel refreshes in place.

## Preview and raw file access

- **Preview** opens a file preview panel (`/ui/files/preview`)
- **Raw file endpoint**: `/ui/files/raw?path=...`
- Thumbnail endpoint exists for image/pdf/video previews (`/ui/files/thumbnail`)

Preview intentionally degrades safely for unsupported or unreadable files.

## Desktop-only integration in Files view

When running in the desktop app, context actions can call the pywebview bridge:

- `window.desktopOpenPath(path)` to reveal a path in Finder/Explorer/Nautilus

This action is hidden in plain browser mode.

## Not yet implemented in this surface

The UI intentionally marks bulk and context actions as not yet implemented:

- bulk move
- bulk rename
- bulk delete
- per-item move/rename/delete from context menu
