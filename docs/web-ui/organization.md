# Organization Workflows (Web UI)

This guide covers the implemented organization dashboard at `/ui/organize`.

## Core workflow

The page is organized as:

1. **Scan and generate plan**
2. **Review plan**
3. **Run/monitor job**
4. **Review history and stats**

## Generate a plan

Use the scan form to provide:

- input directory
- output directory
- methodology
- recursive scan toggle
- skip-existing toggle
- hardlink toggle

Supported methodology options in the current UI:

- `content_based`
- `johnny_decimal`
- `para`
- `date_based`

## Run and monitor

After generating a plan, run execution from the dashboard controls.

The page includes:

- live status updates
- progress rendering
- periodic history refresh
- periodic stats refresh

## History and exports

The dashboard includes history filtering by status and report export paths (JSON/CSV) for completed runs.

## Scope notes

- This page documents the current web organization dashboard only.
- It does not claim background scheduler UX beyond what is currently exposed in the dashboard/routes.
