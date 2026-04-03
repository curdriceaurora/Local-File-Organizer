"""Rule manager — CRUD operations with YAML persistence.

Manages rule sets stored as YAML files in the user's config directory.
Each rule set is a separate ``.yaml`` file.
"""

from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]
from loguru import logger

from file_organizer.config.path_manager import get_config_dir
from file_organizer.config.path_migration import resolve_legacy_path
from file_organizer.services.copilot.rules.models import Rule, RuleSet

_DEFAULT_RULES_DIR = resolve_legacy_path(
    get_config_dir() / "rules",
    Path.home() / ".config" / "file-organizer" / "rules",
)


class RuleManager:
    """CRUD manager for copilot organisation rules.

    Args:
        rules_dir: Directory where rule set YAML files are stored.
    """

    def __init__(self, rules_dir: str | Path | None = None) -> None:
        """Initialize RuleManager."""
        self._rules_dir = Path(rules_dir) if rules_dir else _DEFAULT_RULES_DIR

    @property
    def rules_dir(self) -> Path:
        """Return the rules storage directory."""
        return self._rules_dir

    # ------------------------------------------------------------------
    # Rule-set level CRUD
    # ------------------------------------------------------------------

    def list_rule_sets(self) -> list[str]:
        """List available rule set names.

        Returns:
            Sorted list of rule set names (without ``.yaml`` extension).
        """
        if not self._rules_dir.is_dir():
            return []
        return sorted(p.stem for p in self._rules_dir.glob("*.yaml"))

    def load_rule_set(self, name: str = "default") -> RuleSet:
        """Load a rule set from disk.

        If the file doesn't exist, returns an empty ``RuleSet``.

        Args:
            name: Rule set name.

        Returns:
            The loaded ``RuleSet``.
        """
        path = self._rules_dir / f"{name}.yaml"
        if not path.exists():
            logger.debug("Rule set '{}' not found at {}, returning empty", name, path)
            return RuleSet(name=name)

        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError, ValueError, KeyError):
            logger.warning("Failed to parse rule set '{}'", name, exc_info=True)
            return RuleSet(name=name)

        if not isinstance(raw, dict):
            return RuleSet(name=name)

        return RuleSet.from_dict(raw)

    def save_rule_set(self, rule_set: RuleSet) -> Path:
        """Save a rule set to disk.

        Creates the rules directory if it doesn't exist.

        Args:
            rule_set: The rule set to persist.

        Returns:
            Path to the saved file.
        """
        self._rules_dir.mkdir(parents=True, exist_ok=True)
        path = self._rules_dir / f"{rule_set.name}.yaml"
        content = yaml.dump(
            rule_set.to_dict(),
            default_flow_style=False,
            sort_keys=False,
        )
        path.write_text(content, encoding="utf-8")
        logger.info("Saved rule set '{}' to {}", rule_set.name, path)
        return path

    def delete_rule_set(self, name: str) -> bool:
        """Delete a rule set file.

        Args:
            name: Rule set name.

        Returns:
            True if deleted, False if not found.
        """
        path = self._rules_dir / f"{name}.yaml"
        if not path.exists():
            return False
        path.unlink()
        logger.info("Deleted rule set '{}'", name)
        return True

    # ------------------------------------------------------------------
    # Individual rule CRUD
    # ------------------------------------------------------------------

    def add_rule(self, rule_set_name: str, rule: Rule) -> RuleSet:
        """Add a rule to a rule set.

        Args:
            rule_set_name: Target rule set.
            rule: Rule to add.

        Returns:
            The updated rule set.
        """
        rs = self.load_rule_set(rule_set_name)
        # Prevent duplicate names
        rs.rules = [r for r in rs.rules if r.name != rule.name]
        rs.rules.append(rule)
        self.save_rule_set(rs)
        return rs

    def remove_rule(self, rule_set_name: str, rule_name: str) -> bool:
        """Remove a rule from a rule set by name.

        Args:
            rule_set_name: Target rule set.
            rule_name: Name of the rule to remove.

        Returns:
            True if the rule was found and removed.
        """
        rs = self.load_rule_set(rule_set_name)
        original_count = len(rs.rules)
        rs.rules = [r for r in rs.rules if r.name != rule_name]
        if len(rs.rules) == original_count:
            return False
        self.save_rule_set(rs)
        return True

    def get_rule(self, rule_set_name: str, rule_name: str) -> Rule | None:
        """Get a single rule by name.

        Args:
            rule_set_name: Rule set to search.
            rule_name: Name of the rule.

        Returns:
            The rule if found, else None.
        """
        rs = self.load_rule_set(rule_set_name)
        for r in rs.rules:
            if r.name == rule_name:
                return r
        return None

    def update_rule(self, rule_set_name: str, rule: Rule) -> bool:
        """Update an existing rule (matched by name).

        Args:
            rule_set_name: Target rule set.
            rule: Rule with updated values.

        Returns:
            True if the rule was found and updated.
        """
        rs = self.load_rule_set(rule_set_name)
        for i, existing in enumerate(rs.rules):
            if existing.name == rule.name:
                rs.rules[i] = rule
                self.save_rule_set(rs)
                return True
        return False

    def toggle_rule(self, rule_set_name: str, rule_name: str) -> bool | None:
        """Toggle a rule's enabled state.

        Args:
            rule_set_name: Target rule set.
            rule_name: Rule to toggle.

        Returns:
            The new enabled state, or None if rule not found.
        """
        rs = self.load_rule_set(rule_set_name)
        for r in rs.rules:
            if r.name == rule_name:
                r.enabled = not r.enabled
                self.save_rule_set(rs)
                return r.enabled
        return None
