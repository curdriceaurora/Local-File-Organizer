#!/usr/bin/env python3
"""
File Organizer v2 - End-to-End Demo

This demo showcases the 100% quality text processing with real files.

Supports: PDF, DOCX, TXT, MD, CSV, XLSX, PPT, PPTX, EPUB
Coming soon: Images, Videos, Audio
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import argparse
from file_organizer.core import FileOrganizer
from loguru import logger
from rich.console import Console

# Configure logging
logger.remove()
logger.add(sys.stderr, level="INFO", format="<level>{level: <8}</level> | {message}")

console = Console()


def create_sample_files(directory: Path) -> None:
    """Create sample files for demonstration.

    Args:
        directory: Directory to create files in
    """
    directory.mkdir(parents=True, exist_ok=True)

    # 1. Budget spreadsheet
    (directory / "budget_2024.txt").write_text("""
2024 Annual Budget Summary

Revenue:
- Product Sales: $1,250,000
- Service Contracts: $450,000
- Consulting: $180,000
Total Revenue: $1,880,000

Expenses:
- Salaries: $980,000
- Infrastructure: $230,000
- Marketing: $145,000
- R&D: $195,000
Total Expenses: $1,550,000

Net Profit: $330,000 (17.6% margin)

Key Investments:
- Cloud infrastructure upgrade: $85,000
- New product development: $120,000
- Team expansion: $200,000
""".strip())

    # 2. Meeting notes
    (directory / "team_meeting_notes.md").write_text("""
# Sprint Planning Meeting - Jan 2024

## Attendees
Sarah (Product), Mike (Engineering), Lisa (Design), Tom (QA)

## Sprint Goals
1. Complete user authentication redesign
2. Implement dark mode across all components
3. Fix critical bugs in payment processing
4. Improve dashboard performance by 40%

## Technical Decisions
- Migrate to React 18 for better performance
- Implement Redux Toolkit for state management
- Use TypeScript strict mode on all new code
- Switch to Vite for faster build times

## Action Items
- Mike: Set up CI/CD pipeline (Due: Jan 25)
- Lisa: Finalize design system documentation (Due: Jan 20)
- Tom: Write automated tests for auth flow (Due: Jan 30)
- Sarah: User research interviews (Due: Feb 5)

## Blockers
- Waiting on API documentation from backend team
- Need design approval for mobile layouts
""".strip())

    # 3. Technical documentation
    (directory / "api_docs.txt").write_text("""
REST API Documentation v2.0

Base URL: https://api.example.com/v2

Authentication:
All requests require Bearer token in Authorization header:
Authorization: Bearer YOUR_API_KEY

Endpoints:

GET /users
Returns paginated list of users
Parameters:
  - limit (int): Max results per page (default: 50, max: 100)
  - offset (int): Pagination offset (default: 0)
  - sort (string): Sort field (default: created_at)
  - order (string): Sort order: asc or desc (default: desc)

Response 200:
{
  "users": [...],
  "total": 1234,
  "limit": 50,
  "offset": 0
}

POST /users
Create new user account
Body:
{
  "email": "user@example.com",
  "password": "secure_password",
  "name": "John Doe",
  "role": "user"
}

Response 201:
{
  "id": "usr_abc123",
  "email": "user@example.com",
  "created_at": "2024-01-15T10:30:00Z"
}

Error Codes:
- 400: Bad Request (validation failed)
- 401: Unauthorized (invalid or missing token)
- 403: Forbidden (insufficient permissions)
- 404: Not Found
- 429: Too Many Requests (rate limit exceeded)
- 500: Internal Server Error

Rate Limiting:
100 requests per minute per API key
Headers include:
  X-RateLimit-Limit: 100
  X-RateLimit-Remaining: 95
  X-RateLimit-Reset: 1705320000
""".strip())

    # 4. Research paper
    (directory / "ml_research_paper.txt").write_text("""
Transfer Learning in Natural Language Processing

Abstract:
This paper examines the effectiveness of transfer learning techniques in NLP tasks. We demonstrate that pre-trained language models fine-tuned on domain-specific data achieve superior performance compared to models trained from scratch, while requiring significantly less training data and computational resources.

Introduction:
Transfer learning has revolutionized computer vision and is now transforming natural language processing. Pre-trained models like BERT, GPT, and T5 have shown remarkable ability to capture linguistic patterns that transfer across tasks.

Methodology:
We conducted experiments using three pre-trained models (BERT-base, RoBERTa-large, and GPT-3) across five NLP tasks:
1. Sentiment analysis
2. Named entity recognition
3. Question answering
4. Text summarization
5. Machine translation

Each model was fine-tuned on task-specific datasets ranging from 1,000 to 100,000 examples. We measured accuracy, F1 score, and BLEU score as appropriate for each task.

Results:
Transfer learning approaches consistently outperformed baseline models:
- Sentiment analysis: 92.3% accuracy (vs. 78.5% baseline)
- NER: F1 score of 89.7 (vs. 72.4 baseline)
- Question answering: 84.2% exact match (vs. 61.3% baseline)
- Summarization: ROUGE-L of 0.412 (vs. 0.287 baseline)
- Translation: BLEU score of 31.5 (vs. 24.1 baseline)

Remarkably, fine-tuning with just 10% of the training data achieved 95% of the performance obtained with the full dataset.

Conclusion:
Transfer learning enables high-quality NLP systems with minimal data and compute requirements. This democratizes access to advanced NLP capabilities for researchers and practitioners with limited resources.
""".strip())

    # 5. Recipe
    (directory / "cookie_recipe.md").write_text("""
# Classic Chocolate Chip Cookies

Yield: 48 cookies | Prep: 15 min | Bake: 12 min | Total: 27 min

## Ingredients

### Dry Ingredients
- 2¼ cups (280g) all-purpose flour
- 1 tsp baking soda
- 1 tsp salt

### Wet Ingredients
- 1 cup (230g) butter, softened
- ¾ cup (150g) granulated sugar
- ¾ cup (165g) packed brown sugar
- 2 large eggs
- 2 tsp vanilla extract

### Mix-ins
- 2 cups (340g) chocolate chips
- 1 cup (120g) chopped walnuts (optional)

## Instructions

1. **Preheat** oven to 375°F (190°C).

2. **Mix dry ingredients**: Combine flour, baking soda, and salt in a bowl.

3. **Cream butter and sugars**: Beat butter and both sugars until light and fluffy (2-3 minutes).

4. **Add eggs and vanilla**: Beat in eggs one at a time, then add vanilla.

5. **Combine**: Gradually stir in flour mixture until just combined.

6. **Add chocolate**: Fold in chocolate chips and walnuts.

7. **Scoop**: Drop rounded tablespoons of dough onto ungreased baking sheets, 2 inches apart.

8. **Bake**: 9-11 minutes or until golden brown around edges.

9. **Cool**: Let cool on baking sheet for 2 minutes, then transfer to wire rack.

## Pro Tips
- Use room temperature ingredients for better mixing
- Don't overbake - cookies continue cooking on the hot pan
- For chewier cookies, slightly underbake
- For crispier cookies, bake an extra 1-2 minutes
- Dough can be frozen for up to 3 months

## Storage
Store in airtight container at room temperature for up to 1 week.
""".strip())

    # 6. Travel itinerary
    (directory / "paris_trip_2024.txt").write_text("""
Paris Vacation Itinerary - April 2024

Day 1: Arrival & Eiffel Tower
- 10:00 AM: Arrive at Charles de Gaulle Airport
- 12:00 PM: Check into hotel (Le Marais district)
- 2:00 PM: Lunch at local café
- 4:00 PM: Visit Eiffel Tower (pre-booked tickets)
- 7:00 PM: Seine River cruise at sunset
- 9:00 PM: Dinner in Latin Quarter

Day 2: Museums & Art
- 9:00 AM: Louvre Museum (arrive early to avoid crowds)
- Must see: Mona Lisa, Venus de Milo, Winged Victory
- 1:00 PM: Lunch in Tuileries Garden
- 3:00 PM: Musée d'Orsay (Impressionist art)
- 7:00 PM: Dinner in Saint-Germain-des-Prés

Day 3: Historic Paris
- 10:00 AM: Notre-Dame Cathedral (exterior only, under restoration)
- 11:30 AM: Sainte-Chapelle (stunning stained glass)
- 1:00 PM: Lunch on Île de la Cité
- 3:00 PM: Walk through Le Marais district
- 5:00 PM: Visit Place des Vosges
- 8:00 PM: Traditional French dinner

Day 4: Versailles
- 8:00 AM: Train to Versailles
- 9:30 AM: Palace of Versailles (full day)
- Explore: Hall of Mirrors, Royal Apartments, Gardens
- 1:00 PM: Lunch at château café
- 3:00 PM: Marie Antoinette's Estate
- 6:00 PM: Return to Paris
- 8:00 PM: Casual dinner near hotel

Day 5: Montmartre & Shopping
- 10:00 AM: Montmartre walking tour
- 11:30 AM: Sacré-Cœur Basilica
- 1:00 PM: Lunch in Montmartre
- 3:00 PM: Shopping on Champs-Élysées
- 6:00 PM: Arc de Triomphe
- 8:00 PM: Farewell dinner at traditional bistro

Budget Estimate:
- Flights: $800 per person
- Hotel (4 nights): $600
- Food: $400
- Attractions: $200
- Transportation: $100
- Souvenirs: $150
Total: ~$2,250 per person
""".strip())

    # 7. Product requirements
    (directory / "feature_requirements.md").write_text("""
# Feature Requirements: Dark Mode Implementation

## Overview
Implement system-wide dark mode to reduce eye strain and improve user experience in low-light environments.

## Business Goals
- Increase user engagement during evening hours (currently 40% of traffic)
- Improve accessibility for light-sensitive users
- Match competitor features (3 of top 5 competitors have dark mode)
- Reduce battery usage on mobile devices by ~15%

## User Stories

### As a user, I want to...
1. Toggle between light and dark themes
2. Have the theme persist across sessions
3. See smooth transitions when switching themes
4. Have all UI components properly styled in dark mode
5. Option to follow system preference (auto mode)

## Technical Requirements

### Frontend
- Add theme context provider (React Context API)
- Implement CSS variables for theme colors
- Create dark mode versions of all components
- Support three modes: light, dark, auto
- Store preference in localStorage
- Smooth transition animations (200ms)

### Design Specifications
- Background: #1a1a1a
- Surface: #2d2d2d
- Primary text: #e0e0e0
- Secondary text: #a0a0a0
- Accent color: #4a9eff
- Ensure WCAG AA contrast ratios (4.5:1 minimum)

### Components to Update
- [ ] Navigation bar
- [ ] Sidebar
- [ ] Cards and panels
- [ ] Forms and inputs
- [ ] Buttons
- [ ] Tables
- [ ] Modals and dialogs
- [ ] Toast notifications
- [ ] Charts and graphs

## Acceptance Criteria
1. Users can toggle dark mode from settings menu
2. Theme preference persists across browser sessions
3. All text meets WCAG AA contrast requirements
4. No visual glitches or flash of unstyled content
5. Theme changes smoothly with animation
6. Auto mode respects system preferences
7. Works on all supported browsers (Chrome, Firefox, Safari, Edge)

## Success Metrics
- 60% of evening users (6 PM - 12 AM) enable dark mode within 2 weeks
- 5% increase in average session duration during evening hours
- User satisfaction score increases by 10+ points
- Zero critical accessibility issues reported

## Timeline
- Design: 1 week
- Development: 2 weeks
- Testing: 1 week
- Launch: Week of Feb 15, 2024

## Dependencies
- Design system update with dark mode tokens
- Backend API support for user preferences
- Mobile app updates for consistency

## Risks & Mitigation
- Risk: Breaking existing styles
  Mitigation: Comprehensive visual regression testing
- Risk: Performance impact from theme switching
  Mitigation: Optimize CSS variables, minimize re-renders
- Risk: Designer availability
  Mitigation: Start with existing design system patterns
""".strip())

    console.print(f"[green]✓[/green] Created {7} sample files in {directory}")


def main():
    """Run the end-to-end demo."""
    parser = argparse.ArgumentParser(
        description="File Organizer v2 - End-to-End Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Demo with sample files (dry run)
  python demo.py --sample --dry-run

  # Actually organize sample files
  python demo.py --sample

  # Organize your own directory
  python demo.py --input ~/Documents/messy_files --output ~/Documents/organized

  # Organize with detailed logging
  python demo.py --input ./files --output ./organized --verbose
        """
    )

    parser.add_argument(
        "--sample",
        action="store_true",
        help="Use sample files for demo"
    )
    parser.add_argument(
        "--input",
        type=str,
        help="Input directory with files to organize"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output directory for organized files"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate organization without moving files"
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Copy files instead of creating hardlinks"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Configure logging
    if args.verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")

    # Banner
    console.print("\n" + "=" * 70, style="bold blue")
    console.print("File Organizer v2 - End-to-End Demo", style="bold blue", justify="center")
    console.print("AI-Powered File Organization with 100% Quality", style="dim", justify="center")
    console.print("=" * 70 + "\n", style="bold blue")

    # Determine input/output paths
    if args.sample:
        console.print("[yellow]Running with sample files...[/yellow]\n")
        input_path = Path(__file__).parent / "demo_files"
        output_path = Path(__file__).parent / "demo_organized"

        # Create sample files
        console.print("[bold]Creating sample files...[/bold]")
        create_sample_files(input_path)
    else:
        if not args.input:
            console.print("[red]Error: --input required (or use --sample)[/red]")
            parser.print_help()
            sys.exit(1)

        input_path = Path(args.input)
        output_path = Path(args.output) if args.output else input_path.parent / "organized"

    console.print(f"[bold]Input:[/bold]  {input_path}")
    console.print(f"[bold]Output:[/bold] {output_path}")

    if args.dry_run:
        console.print("[yellow]Mode:[/yellow] DRY RUN (no files will be moved)")
    else:
        console.print("[green]Mode:[/green] LIVE (files will be organized)")

    # Create organizer
    organizer = FileOrganizer(
        dry_run=args.dry_run,
        use_hardlinks=not args.copy,
    )

    # Run organization
    try:
        result = organizer.organize(input_path, output_path)

        # Success
        if result.processed_files > 0:
            console.print("\n[bold green]🎉 Success![/bold green]")

            if not args.dry_run:
                console.print(f"\nYour files are organized in: [cyan]{output_path}[/cyan]")
            else:
                console.print("\n[yellow]To actually organize files, run without --dry-run[/yellow]")

        sys.exit(0)

    except KeyboardInterrupt:
        console.print("\n\n[yellow]Operation cancelled by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        logger.exception("Demo failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
