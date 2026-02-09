# PARA + Johnny Decimal Setup

This guide shows how to enable PARA or Johnny Decimal methodologies, then preview them in the TUI.

## Set the Default Methodology

```bash
file-organizer config edit --methodology para
```

Switch to Johnny Decimal:

```bash
file-organizer config edit --methodology jd
```

## Preview in the TUI

1. Launch the TUI: `file-organizer tui`.
2. Press `4` for Methodology.
3. Press `p` for PARA or `j` for Johnny Decimal.

## Configure PARA

Add a `para` block in your config profile:

```yaml
para:
  auto_categorize: true
  enable_ai_heuristic: false
  project_dir: "Projects"
  area_dir: "Areas"
  resource_dir: "Resources"
  archive_dir: "Archive"
```

## Configure Johnny Decimal

Johnny Decimal uses a numbering scheme with areas and categories:

```yaml
johnny_decimal:
  scheme:
    name: "default"
    areas:
      - area_range_start: 10
        area_range_end: 19
        name: "Projects"
    categories:
      - area: 10
        category: 11
        name: "Active"
  migration:
    preserve_original_names: true
    create_backups: true
  compatibility:
    para_integration:
      enabled: false
```

## Learn More

- [PARA methodology](../phase-3/para-methodology.md)
- [Johnny Decimal guide](../phase-3/johnny-decimal.md)
