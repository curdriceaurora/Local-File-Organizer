"""
Auto-Tagging CLI Commands

Command-line interface for the auto-tagging system.
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional
import json

from ..services.auto_tagging import AutoTaggingService


def setup_autotag_parser(subparsers):
    """
    Set up the autotag command parser.

    Args:
        subparsers: Argument parser subparsers object
    """
    parser = subparsers.add_parser(
        'autotag',
        help='Auto-tagging suggestions and management'
    )

    autotag_subparsers = parser.add_subparsers(dest='autotag_command')

    # Suggest command
    suggest_parser = autotag_subparsers.add_parser(
        'suggest',
        help='Suggest tags for files'
    )
    suggest_parser.add_argument(
        'files',
        nargs='+',
        type=str,
        help='Files to suggest tags for'
    )
    suggest_parser.add_argument(
        '--existing-tags',
        nargs='*',
        help='Tags already applied to the file'
    )
    suggest_parser.add_argument(
        '--top-n',
        type=int,
        default=10,
        help='Maximum number of suggestions (default: 10)'
    )
    suggest_parser.add_argument(
        '--min-confidence',
        type=float,
        default=40.0,
        help='Minimum confidence threshold (default: 40)'
    )
    suggest_parser.add_argument(
        '--json',
        action='store_true',
        help='Output in JSON format'
    )

    # Apply command
    apply_parser = autotag_subparsers.add_parser(
        'apply',
        help='Apply tags to files and record for learning'
    )
    apply_parser.add_argument(
        'file',
        type=str,
        help='File to tag'
    )
    apply_parser.add_argument(
        'tags',
        nargs='+',
        help='Tags to apply'
    )

    # Popular command
    popular_parser = autotag_subparsers.add_parser(
        'popular',
        help='Show most popular tags'
    )
    popular_parser.add_argument(
        '--limit',
        type=int,
        default=20,
        help='Number of tags to show (default: 20)'
    )

    # Recent command
    recent_parser = autotag_subparsers.add_parser(
        'recent',
        help='Show recently used tags'
    )
    recent_parser.add_argument(
        '--days',
        type=int,
        default=30,
        help='Number of days to look back (default: 30)'
    )
    recent_parser.add_argument(
        '--limit',
        type=int,
        default=20,
        help='Number of tags to show (default: 20)'
    )

    # Analyze command
    analyze_parser = autotag_subparsers.add_parser(
        'analyze',
        help='Analyze file content for tags'
    )
    analyze_parser.add_argument(
        'file',
        type=str,
        help='File to analyze'
    )
    analyze_parser.add_argument(
        '--keywords',
        action='store_true',
        help='Show keyword analysis'
    )
    analyze_parser.add_argument(
        '--entities',
        action='store_true',
        help='Show entity extraction'
    )

    # Batch command
    batch_parser = autotag_subparsers.add_parser(
        'batch',
        help='Batch tag suggestion for multiple files'
    )
    batch_parser.add_argument(
        'directory',
        type=str,
        help='Directory to process'
    )
    batch_parser.add_argument(
        '--pattern',
        type=str,
        default='*',
        help='File pattern (default: *)'
    )
    batch_parser.add_argument(
        '--recursive',
        action='store_true',
        help='Process directories recursively'
    )
    batch_parser.add_argument(
        '--output',
        type=str,
        help='Output file for results (JSON)'
    )


def handle_autotag_command(args):
    """
    Handle autotag commands.

    Args:
        args: Parsed command-line arguments
    """
    # Initialize service
    service = AutoTaggingService()

    if args.autotag_command == 'suggest':
        handle_suggest(service, args)
    elif args.autotag_command == 'apply':
        handle_apply(service, args)
    elif args.autotag_command == 'popular':
        handle_popular(service, args)
    elif args.autotag_command == 'recent':
        handle_recent(service, args)
    elif args.autotag_command == 'analyze':
        handle_analyze(service, args)
    elif args.autotag_command == 'batch':
        handle_batch(service, args)
    else:
        print("No autotag subcommand specified. Use --help for usage.")
        sys.exit(1)


def handle_suggest(service: AutoTaggingService, args):
    """Handle suggest command."""
    results = []

    for file_str in args.files:
        file_path = Path(file_str).resolve()

        if not file_path.exists():
            print(f"Error: File not found: {file_path}", file=sys.stderr)
            continue

        # Get recommendations
        recommendation = service.suggest_tags(
            file_path,
            existing_tags=args.existing_tags,
            top_n=args.top_n
        )

        # Filter by confidence
        filtered_suggestions = [
            s for s in recommendation.suggestions
            if s.confidence >= args.min_confidence
        ]

        if args.json:
            results.append({
                'file': str(file_path),
                'suggestions': [s.to_dict() for s in filtered_suggestions]
            })
        else:
            print(f"\n{'='*60}")
            print(f"Tag suggestions for: {file_path.name}")
            print(f"{'='*60}")

            if not filtered_suggestions:
                print("No suggestions meeting confidence threshold.")
            else:
                for i, suggestion in enumerate(filtered_suggestions, 1):
                    confidence_bar = '█' * int(suggestion.confidence / 5)
                    print(f"\n{i}. {suggestion.tag}")
                    print(f"   Confidence: {suggestion.confidence:.1f}% {confidence_bar}")
                    print(f"   Source: {suggestion.source}")
                    print(f"   Reason: {suggestion.reasoning}")

    if args.json:
        print(json.dumps(results, indent=2))


def handle_apply(service: AutoTaggingService, args):
    """Handle apply command."""
    file_path = Path(args.file).resolve()

    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    # Record tag application
    service.record_tag_usage(file_path, args.tags)

    print(f"✓ Applied tags to {file_path.name}:")
    for tag in args.tags:
        print(f"  - {tag}")
    print("\nTags recorded for learning.")


def handle_popular(service: AutoTaggingService, args):
    """Handle popular command."""
    popular = service.get_popular_tags(limit=args.limit)

    if not popular:
        print("No tag usage data yet.")
        return

    print(f"\nMost Popular Tags (Top {args.limit}):")
    print(f"{'='*40}")

    for i, (tag, count) in enumerate(popular, 1):
        bar = '█' * min(count, 50)
        print(f"{i:2d}. {tag:20s} {count:4d} {bar}")


def handle_recent(service: AutoTaggingService, args):
    """Handle recent command."""
    recent = service.get_recent_tags(days=args.days, limit=args.limit)

    if not recent:
        print(f"No tags used in the last {args.days} days.")
        return

    print(f"\nRecently Used Tags (Last {args.days} days):")
    print(f"{'='*40}")

    for i, tag in enumerate(recent, 1):
        print(f"{i:2d}. {tag}")


def handle_analyze(service: AutoTaggingService, args):
    """Handle analyze command."""
    file_path = Path(args.file).resolve()

    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    print(f"\nContent Analysis: {file_path.name}")
    print(f"{'='*60}")

    # Basic tags
    tags = service.content_analyzer.analyze_file(file_path)
    print(f"\nExtracted Tags ({len(tags)}):")
    for tag in tags:
        print(f"  - {tag}")

    # Keywords
    if args.keywords:
        keywords = service.content_analyzer.extract_keywords(file_path, top_n=15)
        print("\nTop Keywords:")
        for keyword, score in keywords:
            print(f"  {keyword:20s} {score:.3f}")

    # Entities
    if args.entities:
        entities = service.content_analyzer.extract_entities(file_path)
        print(f"\nExtracted Entities ({len(entities)}):")
        for entity in entities:
            print(f"  - {entity}")


def handle_batch(service: AutoTaggingService, args):
    """Handle batch command."""
    directory = Path(args.directory).resolve()

    if not directory.is_dir():
        print(f"Error: Not a directory: {directory}", file=sys.stderr)
        sys.exit(1)

    # Find files
    if args.recursive:
        pattern = f"**/{args.pattern}"
    else:
        pattern = args.pattern

    files = list(directory.glob(pattern))
    files = [f for f in files if f.is_file()]

    if not files:
        print(f"No files found matching pattern: {pattern}")
        return

    print(f"Processing {len(files)} files...")

    # Batch recommend
    results = service.recommender.batch_recommend(files, top_n=5)

    # Prepare output
    output_data = []
    for file_path, recommendation in results.items():
        output_data.append({
            'file': str(file_path),
            'suggestions': [
                {
                    'tag': s.tag,
                    'confidence': s.confidence,
                    'source': s.source
                }
                for s in recommendation.suggestions
            ]
        })

    # Save or print
    if args.output:
        output_path = Path(args.output)
        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"✓ Results saved to: {output_path}")
    else:
        print(json.dumps(output_data, indent=2))
