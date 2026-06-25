"""Config-schema migration registry.

F6 (hardening roadmap #159): explicit version-bump handling for
serialized ``AppConfig`` dicts. When :data:`config.schema.CURRENT_SCHEMA_VERSION`
is bumped, register a migration here that transforms the pre-bump
dict shape into the post-bump shape. ``ConfigManager.load`` walks
the registry at read time so old ``config.yaml`` files upgrade
automatically on next launch.

Contract
--------
- Each entry maps a *source* version string to a callable
  ``(data: dict) -> dict`` that returns the post-migration data.
- Migrations chain: if the on-disk version is ``"0.5"`` and current
  is ``"1.5"``, and there are migrations for ``"0.5"`` and ``"1.0"``,
  both run in sequence. The migration for version *X* produces the
  data shape at version *X+1*.
- Migrations must be idempotent — running twice on already-migrated
  data should be a no-op. This simplifies recovery after a partial
  load failure.
- A migration MUST return its result. In-place mutation is permitted
  (the walker passes the dict by reference), but the returned value
  is what the next step receives — returning ``None`` would clobber
  the chain.

Backwards/future-compat
-----------------------
- A config with a version *newer* than ``CURRENT_SCHEMA_VERSION``
  cannot be migrated (we don't have the newer migrations). The
  load path logs a loud WARNING and proceeds best-effort — refusing
  would strand users mid-upgrade.
- A config with a version that has no registered migration AND is
  not the current version is also treated as best-effort with a
  WARNING.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MigrationFn = Callable[[dict[str, object]], dict[str, object]]


@dataclass(frozen=True)
class Migration:
    """A single schema-migration step.

    Codex PRRT_kwDOR_Rkws59hdFY: each migration declares the version
    it produces, so the walker can't silently jump over a gap in the
    registry. Previously the walker used ``_next_version`` to infer
    the post-migration version from the next registered key — which
    applied the wrong transform when the registry had gaps (e.g.
    ``{"0.5", "2.0"}`` with no ``"1.0"``: after the 0.5 migration
    produced 1.0-shaped data, the walker jumped ``current`` to 2.0
    and ran the 2.0 migration on 1.0-shaped data, silently corrupting
    fields).

    Attributes:
        to_version: The schema version this migration produces.
            Must be strictly greater than the key it is registered
            under (enforced at walk time — a non-increasing
            ``to_version`` stops the walk to avoid infinite loops).
        transform: Callable taking a raw config dict and returning
            the post-migration dict. Must be idempotent (rerunning
            it on already-migrated data is a no-op).
    """

    to_version: str
    transform: MigrationFn


# Public registry. Keys are source versions; values declare both the
# transform AND its target version (see :class:`Migration`). Populated
# by bumps to :data:`config.schema.CURRENT_SCHEMA_VERSION` as new
# breaking changes ship. Empty today — the schema is at 1.0 with no
# historical predecessors to migrate from. Tests monkeypatch this dict
# to cover the migration-runs and migration-fails paths.
MIGRATIONS: dict[str, Migration] = {}


def _version_key(version: str) -> tuple[int, ...]:
    """Tuple key for ordering dotted-int version strings.

    Codex PRRT_kwDOR_Rkws59fzVk / coderabbit: string comparison on
    versions is wrong (``"10.0" > "2.0"`` is ``False``
    lexicographically). Parse each component as int so numeric
    ordering holds. Non-numeric components fall back to 0 so
    malformed versions don't crash — migration walker treats them
    as very old and warns.

    Codex PRRT_kwDOR_Rkws59hp2C: trailing-zero components are
    trimmed so semantically-equivalent versions like ``"1.0"`` and
    ``"1.0.0"`` compare equal (``(1,) == (1,)``). Without this,
    a ``"1.0.0"`` on-disk version against a current ``"1.0"`` would
    sort as "newer", triggering future-version warnings and
    bypassing migrations. Mid-stream zeros are preserved so
    ``"1.0.1"`` → ``(1, 0, 1)`` still orders above ``"1.0"`` →
    ``(1,)``. The all-zero case ``"0.0.0"`` collapses to ``(0,)``.
    """
    try:
        components = tuple(int(part) for part in version.split("."))
    except ValueError:
        logger.warning(
            "Non-numeric config version %r; treating as 0.0 for ordering",
            version,
        )
        return (0,)
    while len(components) > 1 and components[-1] == 0:
        components = components[:-1]
    return components


def compare_versions(a: str, b: str) -> int:
    """Return ``-1``/``0``/``1`` for ``a < b`` / ``a == b`` / ``a > b``.

    Public so ``ConfigManager.load`` can do future/past detection
    without reimplementing the comparison. Relies on
    :func:`_version_key` for the actual ordering.
    """
    ka, kb = _version_key(a), _version_key(b)
    if ka == kb:
        return 0
    return -1 if ka < kb else 1


def migrate_to_current(
    data: dict[str, object],
    *,
    from_version: str,
    to_version: str,
) -> dict[str, object]:
    """Walk the migration registry from *from_version* to *to_version*.

    Returns the migrated data dict. Missing migrations are logged
    at WARNING and the data is returned unchanged (best-effort).

    Args:
        data: The serialized config dict as read from YAML.
        from_version: The version stamped in the on-disk config.
        to_version: The version this binary expects
            (typically :data:`config.schema.CURRENT_SCHEMA_VERSION`).

    Returns:
        The (possibly transformed) config dict ready for
        ``AppConfig`` construction.
    """
    # Coderabbit PRRT_kwDOR_Rkws59hgCI: compare numerically so
    # textually-different-but-equivalent versions (e.g. ``"1.0"`` vs
    # ``"1.0.0"``) short-circuit the same way; string equality alone
    # would skip this guard and bail below with a false-positive gap
    # warning.
    if _version_key(from_version) == _version_key(to_version):
        return data

    # Codex PRRT_kwDOR_Rkws59hdFY: follow the chain declared by
    # each migration's ``to_version``, not the next registry key.
    # If ``MIGRATIONS.get(current)`` is ``None`` the chain has a
    # gap and we must stop — applying the next-higher registered
    # migration would treat the data as if it were already at that
    # version.
    current = from_version
    safety_limit = len(MIGRATIONS) + 1  # defensive: no cycles / no infinite walks
    for _ in range(safety_limit):
        if _version_key(current) >= _version_key(to_version):
            return data
        step = MIGRATIONS.get(current)
        if step is None:
            # No migration registered from ``current`` — could be a
            # registry gap (future binary forgot to ship an
            # intermediate) or the on-disk file predates all known
            # migrations. Either way, bail best-effort with a loud
            # warning so the operator sees the gap.
            logger.warning(
                "No migration registered from file_organizer.config version %s; loading "
                "as-is. If fields were renamed or added in a newer schema, "
                "they may fall back to defaults. Target was %s.",
                current,
                to_version,
            )
            return data
        if _version_key(step.to_version) <= _version_key(current):
            # Defensive guard against a misconfigured migration that
            # would otherwise loop forever. Should never hit unless a
            # test monkeypatches the registry with a bad entry.
            logger.error(
                "Migration from %s declares non-increasing target %s; "
                "stopping to avoid infinite loop.",
                current,
                step.to_version,
            )
            return data
        try:
            data = step.transform(data)
        except Exception:
            # Re-raise — the caller (ConfigManager.load) decides
            # whether to log + fall back to defaults. We don't want
            # to swallow here because silent migration failure would
            # produce subtly-wrong config at runtime.
            logger.error(
                "Config migration from version %s failed; the caller will fall back to defaults.",
                current,
                exc_info=True,
            )
            raise
        current = step.to_version
    # Exhausted the safety limit without reaching to_version — should
    # only happen if a pathologically bad registry was installed.
    logger.warning(
        "Config migration did not reach target version %s (stopped at %s after %d steps). Loading as-is.",
        to_version,
        current,
        safety_limit,
    )
    return data
