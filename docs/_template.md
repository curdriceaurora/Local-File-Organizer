# Document Title

<!-- MD041: Every file must begin with an H1 heading. Replace the title above with your document's name. -->

Brief one-sentence description of this document's purpose.

<!-- Keep this opening paragraph short. Readers scan the first line to decide if this is the right doc. -->

---

## Overview

<!-- MD022: Leave a blank line before AND after every heading (including this one). -->
<!-- MD001: Use ## for top-level sections under the H1. Never jump from # to ###. -->

Describe what this document covers and who it is for. Include:

- The primary audience (e.g., end users, developers, operators)
- What the reader will know or be able to do after reading

---

## Configuration

<!-- Each ## section is a self-contained topic. Add or remove sections as needed. -->

Describe the configuration options relevant to this feature.

### Example Configuration File

<!-- MD001: ### is valid here because it is one level below the ## parent. -->
<!-- Do not use #### or deeper unless the hierarchy genuinely requires it. -->

<!-- MD040: Every code fence MUST include a language specifier. Use the closest match: -->
<!--   bash, python, yaml, json, toml, text, markdown, etc.                          -->
<!--   Use "text" when no syntax highlighting applies.                                -->

```yaml
# config.yaml
feature:
  enabled: true
  option_one: "value"
  option_two: 42
```

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `FEATURE_ENABLED` | `true` | Enable or disable the feature |
| `FEATURE_OPTION` | `default` | Controls feature behaviour |

```bash
# Export variables before running the application
export FEATURE_ENABLED=true
export FEATURE_OPTION=custom
```

---

## Usage

Explain the common usage patterns with concrete examples.

```text
# Replace with the actual import path for your module, e.g.:
# from file_organizer.services.your_service import YourClass

instance = YourClass(option_one="value")
result = instance.run()
print(result)
```

Expected output:

```text
Feature ran successfully with option_one=value
```

---

## Reference

<!-- Use this section for tables, option lists, or links to related documentation. -->

### Related Documents

- [Getting Started](getting-started.md) - Installation and first run
- [Configuration Reference](CONFIGURATION.md) - Full list of configuration options
- [CLI Reference](cli-reference.md) - Command-line interface documentation

### See Also

<!-- Add links to external resources, RFCs, or upstream documentation when relevant. -->

- Project README (link to the root `README.md` or relevant top-level doc)
