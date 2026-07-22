# Organization Workflows (Web UI)

This guide covers the implemented organization dashboard at `/ui/organize`.

## Core workflow

The page is organized as:

1. **Scan and generate plan**
2. **Review plan**
3. **Run/monitor job**
4. **Review history and stats**

## Quick workflow: plan, review, run, export

1. Open `/ui/organize` and enter input/output directories.
2. Select methodology (`none`, `para`, or `jd`) and any canonical processing options.
3. Generate the plan and review proposed output paths before execution.
4. Start the run and watch live progress/status updates.
5. Export run output/history as JSON/CSV for follow-up or audit.

## Generate a plan

Use the scan form to provide:

- input directory
- output directory
- methodology
- recursive scan toggle
- hidden-file toggle
- skip-existing toggle
- copy or hardlink transfer mode
- image analysis and audio transcription controls
- text, vision, and transcription model settings
- provider and performance settings

Supported methodology options in the current UI:

- `none`
- `para`
- `jd`

The form maps directly to the shared `OrganizeOptions` contract. Scan counts,
preview operations, and execution use the same recursion and hidden-file
policy. The server stores the canonical serialized plan shown for review and
executes that exact version; it does not recompute or rewrite destinations in
the Web layer.

## Run and monitor

After generating a plan, run execution from the dashboard controls.

The page includes:

- live status updates
- progress rendering
- periodic history refresh
- periodic stats refresh
- queued and scheduled cancellation
- transaction-specific rollback when a completed run supports it

The capability-status panel is generated from the shared registry. It shows
implemented, unverified, and unavailable organization workflows explicitly
instead of inferring support from which buttons happen to be visible.

## History and exports

The dashboard includes history filtering by status and report export paths (JSON/CSV) for completed runs.

## Scope notes

- This page documents the current web organization dashboard only.
- It does not claim background scheduler UX beyond what is currently exposed in the dashboard/routes.
