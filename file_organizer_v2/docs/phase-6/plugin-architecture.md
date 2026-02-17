# Plugin Architecture (Phase 6 Task #239)

## Why This Shape

The plugin system is split into six focused modules so each concern can evolve independently:

- `src/file_organizer/plugins/base.py`: plugin contract and metadata model.
- `src/file_organizer/plugins/registry.py`: discovery, dynamic import, dependency checks, and unload cleanup.
- `src/file_organizer/plugins/lifecycle.py`: explicit lifecycle state transitions.
- `src/file_organizer/plugins/security.py`: policy-driven sandbox checks.
- `src/file_organizer/plugins/config.py`: persisted plugin configuration.
- `src/file_organizer/plugins/hooks.py`: hook/event callback dispatch.

This separation prevents the common failure mode where discovery, lifecycle, and permissions become tightly coupled and difficult to test.

## Runtime Flow

1. `PluginRegistry.discover_plugins()` scans plugin entrypoints (`<plugin>/plugin.py` or single-file plugins).
1. `PluginRegistry.load_plugin(name)` resolves config, loads module, instantiates plugin, validates metadata/dependencies, and calls `on_load()`.
1. `PluginLifecycleManager.enable(name)` calls `on_enable()` and marks state as `enabled`.
1. `PluginLifecycleManager.disable(name)` and `unload(name)` provide deterministic shutdown and module cleanup.

## Security Model

`PluginSandbox` enforces two independent capabilities:

- file path access (`validate_file_access` / `require_file_access`)
- operation permission (`validate_operation` / `require_operation`)

The policy is explicit (`PluginSecurityPolicy`) so future enforcement can be tightened without changing plugin contracts.

## Configuration Model

Each plugin has an isolated JSON config (`PluginConfigManager`):

- `enabled`: runtime default state
- `settings`: arbitrary plugin-specific data
- `permissions`: operation permissions consumed by sandbox policy

Writes are atomic to avoid partial/corrupt config files after crashes.

## Dependency Handling

Dependencies are declared in `PluginMetadata.dependencies`.

Current behavior:

- missing dependency -> load fails with `PluginDependencyError`
- discovered or already loaded dependency -> accepted

This fail-fast strategy avoids partially initialized plugin graphs.

## Hook System

`HookRegistry` supports:

- safe registration/unregistration
- non-fail-fast dispatch (collect callback errors)
- optional fail-fast mode (`stop_on_error=True`)

This allows the app to choose reliability mode per hook path.

## Gotchas

- Plugin metadata `name` must match the discovered plugin key (directory/file stem).
- Plugin modules are imported dynamically; unload removes module entries from `sys.modules`, but plugins should still release external resources in `on_unload()`.
- Sandbox checks are opt-in at plugin call sites; plugin code should call `require_*` before sensitive operations.

## Next Reference

Task #241 builds on this with plugin-facing HTTP APIs, SDK utilities, and examples documented under:

- `docs/phase-6/plugin-development/README.md`

Task #240 adds distribution/install mechanics documented under:

- `docs/phase-6/marketplace.md`
