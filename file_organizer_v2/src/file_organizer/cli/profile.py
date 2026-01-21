"""
Profile Management CLI Commands

Provides command-line interface for all profile management operations including:
- Profile CRUD operations
- Import/Export functionality
- Profile merging
- Template management
- Migration operations
"""

import click
import json
from pathlib import Path
from typing import Optional

from file_organizer.services.intelligence import (
    ProfileManager,
    ProfileExporter,
    ProfileImporter,
    ProfileMigrator,
    ProfileMerger,
    TemplateManager,
    MergeStrategy
)


# Initialize managers (will be done per command to avoid state issues)
def get_profile_manager() -> ProfileManager:
    """Get ProfileManager instance."""
    return ProfileManager()


@click.group(name='profile')
def profile_command():
    """Profile management commands."""
    pass


# ============================================================================
# Profile CRUD Commands
# ============================================================================

@profile_command.command(name='list')
def list_profiles():
    """List all available profiles."""
    try:
        manager = get_profile_manager()
        profiles = manager.list_profiles()

        if not profiles:
            click.echo("No profiles found.")
            return

        active_name = manager._get_active_profile_name()

        click.echo(f"\nProfiles ({len(profiles)} total):")
        click.echo("=" * 80)

        for profile in profiles:
            is_active = " [ACTIVE]" if profile.profile_name == active_name else ""
            click.echo(f"\n• {profile.profile_name}{is_active}")
            click.echo(f"  Description: {profile.description}")
            click.echo(f"  Created: {profile.created}")
            click.echo(f"  Updated: {profile.updated}")

            # Show statistics
            global_prefs = len(profile.preferences.get('global', {}))
            dir_prefs = len(profile.preferences.get('directory_specific', {}))
            click.echo(f"  Preferences: {global_prefs} global, {dir_prefs} directory-specific")

        click.echo("\n" + "=" * 80)

    except Exception as e:
        click.echo(f"Error listing profiles: {e}", err=True)
        raise click.Abort() from e


@profile_command.command(name='create')
@click.argument('name')
@click.option('--description', '-d', default='', help='Profile description')
@click.option('--activate', '-a', is_flag=True, help='Activate profile after creation')
def create_profile(name: str, description: str, activate: bool):
    """Create a new profile."""
    try:
        manager = get_profile_manager()

        # Create profile
        profile = manager.create_profile(name, description)

        if profile is None:
            click.echo(f"Failed to create profile '{name}'", err=True)
            raise click.Abort() from e

        click.echo(f"✓ Created profile: {name}")

        # Activate if requested
        if activate:
            if manager.activate_profile(name):
                click.echo(f"✓ Activated profile: {name}")
            else:
                click.echo("✗ Failed to activate profile", err=True)

    except Exception as e:
        click.echo(f"Error creating profile: {e}", err=True)
        raise click.Abort() from e


@profile_command.command(name='activate')
@click.argument('name')
def activate_profile(name: str):
    """Activate a profile (make it the current active profile)."""
    try:
        manager = get_profile_manager()

        if manager.activate_profile(name):
            click.echo(f"✓ Activated profile: {name}")
        else:
            click.echo(f"✗ Failed to activate profile '{name}'", err=True)
            raise click.Abort() from e

    except Exception as e:
        click.echo(f"Error activating profile: {e}", err=True)
        raise click.Abort() from e


@profile_command.command(name='delete')
@click.argument('name')
@click.option('--force', '-', is_flag=True, help='Force delete even if active')
def delete_profile(name: str, force: bool):
    """Delete a profile."""
    try:
        manager = get_profile_manager()

        # Confirm deletion
        if not force:
            if not click.confirm(f"Are you sure you want to delete profile '{name}'?"):
                click.echo("Cancelled.")
                return

        if manager.delete_profile(name, force=force):
            click.echo(f"✓ Deleted profile: {name}")
        else:
            click.echo(f"✗ Failed to delete profile '{name}'", err=True)
            raise click.Abort() from e

    except Exception as e:
        click.echo(f"Error deleting profile: {e}", err=True)
        raise click.Abort() from e


@profile_command.command(name='current')
def show_current():
    """Show currently active profile."""
    try:
        manager = get_profile_manager()
        profile = manager.get_active_profile()

        if profile is None:
            click.echo("No active profile found.", err=True)
            raise click.Abort() from e

        click.echo(f"\nActive Profile: {profile.profile_name}")
        click.echo("=" * 80)
        click.echo(f"Description: {profile.description}")
        click.echo(f"Version: {profile.profile_version}")
        click.echo(f"Created: {profile.created}")
        click.echo(f"Updated: {profile.updated}")

        # Show statistics
        global_prefs = len(profile.preferences.get('global', {}))
        dir_prefs = len(profile.preferences.get('directory_specific', {}))
        patterns = len(profile.learned_patterns)
        confidence = len(profile.confidence_data)

        click.echo("\nStatistics:")
        click.echo(f"  Global preferences: {global_prefs}")
        click.echo(f"  Directory-specific: {dir_prefs}")
        click.echo(f"  Learned patterns: {patterns}")
        click.echo(f"  Confidence data: {confidence}")
        click.echo("=" * 80 + "\n")

    except Exception as e:
        click.echo(f"Error showing current profile: {e}", err=True)
        raise click.Abort() from e


# ============================================================================
# Export/Import Commands
# ============================================================================

@profile_command.command(name='export')
@click.argument('name')
@click.option('--output', '-o', type=click.Path(), required=True, help='Output file path')
@click.option('--selective', '-s', multiple=True, help='Select specific preferences to export')
def export_profile(name: str, output: str, selective: tuple):
    """Export a profile to JSON file."""
    try:
        manager = get_profile_manager()
        exporter = ProfileExporter(manager)

        output_path = Path(output)

        if selective:
            # Selective export
            success = exporter.export_selective(name, output_path, list(selective))
        else:
            # Full export
            success = exporter.export_profile(name, output_path)

        if success:
            click.echo(f"✓ Exported profile '{name}' to: {output_path}")
        else:
            click.echo("✗ Failed to export profile", err=True)
            raise click.Abort() from e

    except Exception as e:
        click.echo(f"Error exporting profile: {e}", err=True)
        raise click.Abort() from e


@profile_command.command(name='import')
@click.argument('file', type=click.Path(exists=True))
@click.option('--as', 'new_name', help='Import with a different name')
@click.option('--preview', is_flag=True, help='Preview import without applying')
def import_profile(file: str, new_name: Optional[str], preview: bool):
    """Import a profile from JSON file."""
    try:
        manager = get_profile_manager()
        importer = ProfileImporter(manager)

        file_path = Path(file)

        if preview:
            # Show preview
            preview_data = importer.preview_import(file_path)
            if preview_data is None:
                click.echo("✗ Failed to preview import", err=True)
                raise click.Abort() from e

            click.echo("\nImport Preview:")
            click.echo("=" * 80)
            click.echo(f"Profile: {preview_data['profile_name']}")
            click.echo(f"Description: {preview_data['description']}")
            click.echo(f"Version: {preview_data['profile_version']}")
            click.echo(f"Export Type: {preview_data['export_type']}")

            if 'preferences_count' in preview_data:
                click.echo("\nPreferences:")
                for key, count in preview_data['preferences_count'].items():
                    click.echo(f"  {key}: {count}")

            click.echo(f"\nLearned patterns: {preview_data['learned_patterns_count']}")
            click.echo(f"Confidence data: {preview_data['confidence_data_count']}")

            # Show validation
            validation = preview_data['validation']
            click.echo("\nValidation:")
            click.echo(f"  Valid: {validation['valid']}")
            if validation['errors']:
                click.echo(f"  Errors: {', '.join(validation['errors'])}")
            if validation['warnings']:
                click.echo(f"  Warnings: {', '.join(validation['warnings'])}")

            if 'conflicts' in preview_data:
                click.echo("\n⚠ Conflicts detected:")
                click.echo(f"  {preview_data['conflicts']['message']}")

            click.echo("=" * 80 + "\n")
            return

        # Import profile
        profile = importer.import_profile(file_path, new_name)

        if profile is None:
            click.echo("✗ Failed to import profile", err=True)
            raise click.Abort() from e

        click.echo(f"✓ Imported profile: {profile.profile_name}")

    except Exception as e:
        click.echo(f"Error importing profile: {e}", err=True)
        raise click.Abort() from e


# ============================================================================
# Merge Commands
# ============================================================================

@profile_command.command(name='merge')
@click.argument('profiles', nargs=-1, required=True)
@click.option('--output', '-o', required=True, help='Name for merged profile')
@click.option('--strategy', '-s',
              type=click.Choice(['recent', 'frequent', 'confident', 'first', 'last']),
              default='confident',
              help='Merge strategy for conflicts')
@click.option('--show-conflicts', is_flag=True, help='Show conflicts before merging')
def merge_profiles(profiles: tuple, output: str, strategy: str, show_conflicts: bool):
    """Merge multiple profiles into one."""
    try:
        manager = get_profile_manager()
        merger = ProfileMerger(manager)

        profile_list = list(profiles)

        if len(profile_list) < 2:
            click.echo("Error: Need at least 2 profiles to merge", err=True)
            raise click.Abort() from e

        # Show conflicts if requested
        if show_conflicts:
            conflicts = merger.get_merge_conflicts(profile_list)
            if conflicts:
                click.echo("\nConflicts detected:")
                click.echo("=" * 80)
                for key, values in conflicts.items():
                    click.echo(f"\n{key}:")
                    for i, value in enumerate(values, 1):
                        click.echo(f"  {i}. {value}")
                click.echo("=" * 80 + "\n")

                if not click.confirm("Continue with merge?"):
                    click.echo("Cancelled.")
                    return
            else:
                click.echo("No conflicts detected.\n")

        # Perform merge
        merged = merger.merge_profiles(profile_list, strategy, output)

        if merged is None:
            click.echo("✗ Failed to merge profiles", err=True)
            raise click.Abort() from e

        click.echo(f"✓ Merged {len(profile_list)} profiles into: {output}")
        click.echo(f"  Strategy used: {strategy}")

    except Exception as e:
        click.echo(f"Error merging profiles: {e}", err=True)
        raise click.Abort() from e


# ============================================================================
# Template Commands
# ============================================================================

@profile_command.group(name='template')
def template_commands():
    """Template management commands."""
    pass


@template_commands.command(name='list')
def list_templates():
    """List all available templates."""
    try:
        manager = get_profile_manager()
        template_manager = TemplateManager(manager)

        templates = template_manager.list_templates()

        click.echo(f"\nAvailable Templates ({len(templates)}):")
        click.echo("=" * 80)

        for template_name in templates:
            template = template_manager.get_template(template_name)
            if template:
                click.echo(f"\n• {template_name}")
                click.echo(f"  {template['description']}")

        click.echo("\n" + "=" * 80)

    except Exception as e:
        click.echo(f"Error listing templates: {e}", err=True)
        raise click.Abort() from e


@template_commands.command(name='preview')
@click.argument('name')
def preview_template(name: str):
    """Preview a template."""
    try:
        manager = get_profile_manager()
        template_manager = TemplateManager(manager)

        preview = template_manager.preview_template(name)

        if preview is None:
            click.echo(f"✗ Template '{name}' not found", err=True)
            raise click.Abort() from e

        click.echo(f"\nTemplate Preview: {preview['name']}")
        click.echo("=" * 80)
        click.echo(f"Description: {preview['description']}")

        click.echo("\nPreferences Summary:")
        summary = preview['preferences_summary']
        click.echo(f"  Naming patterns: {', '.join(summary['naming_patterns'])}")
        click.echo(f"  Folder mappings: {', '.join(summary['folder_mappings'])}")
        click.echo(f"  Category overrides: {summary['category_overrides']}")

        click.echo(f"\nLearned patterns: {', '.join(preview['learned_patterns'])}")

        click.echo("\nConfidence levels:")
        for key, value in preview['confidence_levels'].items():
            click.echo(f"  {key}: {value}")

        click.echo("=" * 80 + "\n")

    except Exception as e:
        click.echo(f"Error previewing template: {e}", err=True)
        raise click.Abort() from e


@template_commands.command(name='apply')
@click.argument('template_name')
@click.argument('profile_name')
@click.option('--activate', '-a', is_flag=True, help='Activate profile after creation')
def apply_template(template_name: str, profile_name: str, activate: bool):
    """Create a profile from a template."""
    try:
        manager = get_profile_manager()
        template_manager = TemplateManager(manager)

        profile = template_manager.create_profile_from_template(template_name, profile_name)

        if profile is None:
            click.echo("✗ Failed to create profile from template", err=True)
            raise click.Abort() from e

        click.echo(f"✓ Created profile '{profile_name}' from template '{template_name}'")

        if activate:
            if manager.activate_profile(profile_name):
                click.echo(f"✓ Activated profile: {profile_name}")
            else:
                click.echo("✗ Failed to activate profile", err=True)

    except Exception as e:
        click.echo(f"Error applying template: {e}", err=True)
        raise click.Abort() from e


# ============================================================================
# Migration Commands
# ============================================================================

@profile_command.command(name='migrate')
@click.argument('name')
@click.option('--to-version', required=True, help='Target version')
@click.option('--no-backup', is_flag=True, help='Skip backup before migration')
def migrate_profile(name: str, to_version: str, no_backup: bool):
    """Migrate a profile to a different version."""
    try:
        manager = get_profile_manager()
        migrator = ProfileMigrator(manager)

        backup = not no_backup

        success = migrator.migrate_version(name, to_version, backup=backup)

        if success:
            click.echo(f"✓ Migrated profile '{name}' to version {to_version}")
        else:
            click.echo("✗ Failed to migrate profile", err=True)
            raise click.Abort() from e

    except Exception as e:
        click.echo(f"Error migrating profile: {e}", err=True)
        raise click.Abort() from e


@profile_command.command(name='validate')
@click.argument('name')
def validate_profile(name: str):
    """Validate a profile."""
    try:
        manager = get_profile_manager()
        migrator = ProfileMigrator(manager)

        if migrator.validate_migration(name):
            click.echo(f"✓ Profile '{name}' is valid")
        else:
            click.echo(f"✗ Profile '{name}' validation failed", err=True)
            raise click.Abort() from e

    except Exception as e:
        click.echo(f"Error validating profile: {e}", err=True)
        raise click.Abort() from e


# Export all commands
__all__ = [
    'profile_command',
    'list_profiles',
    'create_profile',
    'activate_profile',
    'delete_profile',
    'show_current',
    'export_profile',
    'import_profile',
    'merge_profiles',
    'template_commands',
    'list_templates',
    'preview_template',
    'apply_template',
    'migrate_profile',
    'validate_profile',
]
