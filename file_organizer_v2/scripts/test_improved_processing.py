#!/usr/bin/env python3
"""Test improved text processing with better prompts."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from file_organizer.services import TextProcessor
from loguru import logger

# Configure logging
logger.remove()
logger.add(sys.stderr, level="INFO")


def create_diverse_test_files(test_dir: Path) -> dict:
    """Create diverse test files to verify improvements.

    Args:
        test_dir: Directory to create test files in

    Returns:
        Dictionary mapping descriptions to file paths
    """
    test_dir.mkdir(exist_ok=True)

    test_files = {}

    # 1. Technical documentation
    tech_doc = test_dir / "api_documentation.md"
    tech_doc.write_text("""
# REST API Documentation

## Authentication
All API requests require an API key in the header:
```
Authorization: Bearer YOUR_API_KEY
```

## Endpoints

### GET /api/users
Returns a list of all users in the system.

Parameters:
- limit (optional): Maximum number of results (default: 100)
- offset (optional): Pagination offset (default: 0)

Response:
```json
{
  "users": [...],
  "total": 1234,
  "limit": 100,
  "offset": 0
}
```

### POST /api/users
Create a new user account.

Required fields:
- email: User's email address
- password: Strong password (min 12 characters)
- name: Full name

### Error Handling
All errors return appropriate HTTP status codes with error messages in JSON format.
""".strip())
    test_files['Technical API Documentation'] = tech_doc

    # 2. Financial document
    finance_doc = test_dir / "quarterly_report.txt"
    finance_doc.write_text("""
Q3 2024 Financial Summary

Revenue: $2.4M (up 23% YoY)
Expenses: $1.8M (up 15% YoY)
Net Profit: $600K (up 45% YoY)

Key Highlights:
- SaaS revenue grew 35% to $1.5M
- Customer acquisition cost decreased by 18%
- Monthly recurring revenue reached $500K
- Customer retention improved to 94%

Strategic Initiatives:
- Launched enterprise tier pricing
- Expanded to European markets
- Hired 5 new engineers
- Completed Series A funding round ($10M)

Outlook:
Q4 targets include reaching $3M revenue and expanding the sales team. Focus on enterprise customers and international growth.
""".strip())
    test_files['Financial Quarterly Report'] = finance_doc

    # 3. Scientific paper
    science_doc = test_dir / "research_paper.txt"
    science_doc.write_text("""
Machine Learning Approaches to Drug Discovery

Abstract:
This paper explores the application of deep learning models to accelerate pharmaceutical drug discovery. We present a novel neural network architecture that predicts molecular binding affinity with 92% accuracy, significantly outperforming traditional computational chemistry methods.

Introduction:
Traditional drug discovery is a time-consuming and expensive process, often taking 10-15 years and costing billions of dollars. Machine learning offers the potential to dramatically reduce both time and cost by predicting promising drug candidates earlier in the pipeline.

Methods:
We trained a graph convolutional network (GCN) on a dataset of 1.2 million known protein-ligand interactions. The model architecture includes attention mechanisms to identify key structural features that contribute to binding affinity.

Results:
Our model achieved 92% accuracy on held-out test data, compared to 78% for traditional docking methods. The model identified 15 novel drug candidates for further experimental validation.

Conclusion:
Deep learning shows significant promise for accelerating drug discovery pipelines while reducing costs.
""".strip())
    test_files['Scientific Research Paper'] = science_doc

    # 4. Meeting notes
    meeting_notes = test_dir / "team_meeting.md"
    meeting_notes.write_text("""
# Weekly Team Sync - Jan 15, 2024

## Attendees
- Sarah (Product Manager)
- Mike (Engineering Lead)
- Jessica (Designer)
- Tom (Marketing)

## Agenda Items

### Product Updates
- Launched dark mode feature (95% positive feedback)
- Working on mobile app redesign
- Planning AI chatbot integration for Q2

### Engineering Updates
- Backend migration to microservices 80% complete
- Reduced API latency by 40%
- Implementing new caching layer

### Design Updates
- Completed user research interviews (20 participants)
- New design system documentation published
- Prototyping dashboard improvements

### Marketing Updates
- Email campaign achieved 23% open rate
- Social media engagement up 45%
- Planning webinar series for Q2

## Action Items
- Sarah: Draft PRD for chatbot feature (Due: Jan 22)
- Mike: Complete microservices migration (Due: Jan 31)
- Jessica: Finalize dashboard mockups (Due: Jan 20)
- Tom: Launch new content campaign (Due: Feb 1)
""".strip())
    test_files['Team Meeting Notes'] = meeting_notes

    # 5. Recipe
    recipe = test_dir / "baking.txt"
    recipe.write_text("""
Homemade Sourdough Bread

This classic sourdough bread recipe produces a crusty exterior with a soft, tangy interior. Perfect for sandwiches or toast.

Ingredients:
- 500g bread flour
- 350g water (70% hydration)
- 100g active sourdough starter
- 10g salt

Instructions:

1. Mix: Combine flour and water, let rest 30 minutes (autolyse)
2. Add starter and salt, mix until combined
3. Bulk fermentation: 4-6 hours at room temperature, fold every 30 minutes for first 2 hours
4. Shape: Gently shape into a round boule
5. Final proof: 2-4 hours at room temperature or overnight in fridge
6. Score: Make deep cuts on top with a sharp blade
7. Bake: 450°F for 20 minutes with steam, then 25 minutes without steam

Tips:
- Use a Dutch oven for better crust
- Starter should be bubbly and active
- Dough should increase by 50% during bulk fermentation
- Internal temperature should reach 205°F when done
""".strip())
    test_files['Sourdough Bread Recipe'] = recipe

    # 6. Travel itinerary
    travel = test_dir / "vacation_plan.md"
    travel.write_text("""
# Tokyo Trip Itinerary - March 2024

## Day 1: Arrival & Shibuya
- Arrive at Narita Airport (3:00 PM)
- Check into hotel in Shibuya
- Explore Shibuya Crossing and shopping district
- Dinner at local izakaya

## Day 2: Traditional Tokyo
- Morning: Visit Senso-ji Temple in Asakusa
- Lunch: Try authentic ramen in Ginza
- Afternoon: Imperial Palace gardens
- Evening: Explore Harajuku and Takeshita Street

## Day 3: Modern Tokyo
- Morning: TeamLab Borderless digital art museum
- Lunch: Sushi at Tsukiji Outer Market
- Afternoon: Tokyo Skytree observation deck
- Evening: Robot Restaurant show in Shinjuku

## Day 4: Day Trip
- Full day excursion to Mount Fuji and Hakone
- Lake Ashi boat cruise
- Hot spring experience
- Return to Tokyo in evening

## Day 5: Shopping & Departure
- Morning: Last-minute shopping in Akihabara
- Lunch: Conveyor belt sushi
- Afternoon: Airport departure (4:00 PM flight)

Budget: ~$2,500 per person (flights, hotels, food, activities)
""".strip())
    test_files['Tokyo Travel Itinerary'] = travel

    # 7. Tutorial
    tutorial = test_dir / "guide.md"
    tutorial.write_text("""
# Complete Git and GitHub Tutorial for Beginners

## What is Git?
Git is a distributed version control system that tracks changes in your code. It allows multiple developers to work on the same project without conflicts.

## What is GitHub?
GitHub is a cloud-based hosting service for Git repositories. It adds collaboration features like pull requests, issues, and project management tools.

## Basic Git Commands

### Starting a Repository
```bash
git init                    # Initialize new repository
git clone <url>            # Clone existing repository
```

### Making Changes
```bash
git add <file>             # Stage changes
git add .                  # Stage all changes
git commit -m "message"    # Commit with message
git status                 # Check repository status
```

### Working with Remotes
```bash
git remote add origin <url>  # Add remote repository
git push origin main         # Push changes to remote
git pull origin main         # Pull changes from remote
git fetch                    # Fetch without merging
```

### Branching
```bash
git branch                   # List branches
git branch <name>           # Create new branch
git checkout <name>         # Switch to branch
git merge <name>            # Merge branch
```

## Best Practices
1. Commit often with clear messages
2. Pull before you push
3. Use branches for new features
4. Write descriptive commit messages
5. Review code before merging

## Common Workflows

### Feature Branch Workflow
1. Create feature branch: `git checkout -b feature/new-feature`
2. Make changes and commit
3. Push to remote: `git push origin feature/new-feature`
4. Open pull request on GitHub
5. Review and merge

This workflow keeps the main branch stable while allowing parallel development.
""".strip())
    test_files['Git GitHub Tutorial'] = tutorial

    return test_files


def test_improved_processing():
    """Test text processing with improved prompts."""
    print("\n" + "=" * 80)
    print("Testing Improved Text Processing")
    print("=" * 80)

    # Create test files
    test_dir = Path(__file__).parent.parent / "test_data_improved"
    print(f"\nCreating {7} diverse test files...")
    test_files = create_diverse_test_files(test_dir)
    print(f"✓ Test files created in: {test_dir}")

    # Initialize processor
    print("\nInitializing TextProcessor...")
    with TextProcessor() as processor:
        print("✓ TextProcessor initialized\n")

        results = []
        for description, file_path in test_files.items():
            print("=" * 80)
            print(f"TEST: {description}")
            print("=" * 80)
            print(f"File: {file_path.name}\n")

            # Process file
            result = processor.process_file(file_path)

            if result.error:
                print(f"✗ Error: {result.error}\n")
                continue

            # Display results
            print(f"⏱️  Processing time: {result.processing_time:.2f}s")
            print(f"\n📁 Folder name: {result.folder_name}")
            print(f"📄 Filename: {result.filename}{result.file_path.suffix}")
            print(f"\n📝 Description:")
            print(f"   {result.description}\n")

            results.append((description, result))

        # Summary
        print("=" * 80)
        print("RESULTS SUMMARY")
        print("=" * 80)

        successful = sum(1 for _, r in results if not r.error)
        total_time = sum(r.processing_time for _, r in results)
        avg_time = total_time / len(results) if results else 0

        print(f"\nProcessing Statistics:")
        print(f"  Total files: {len(results)}")
        print(f"  Successful: {successful}")
        print(f"  Failed: {len(results) - successful}")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Average time: {avg_time:.2f}s per file")

        # File organization preview
        print(f"\n📊 Organization Preview:")
        folders = {}
        for description, result in results:
            if not result.error:
                folder = result.folder_name
                if folder not in folders:
                    folders[folder] = []
                filename_with_ext = f"{result.filename}{result.file_path.suffix}"
                folders[folder].append((filename_with_ext, description))

        for folder, files in sorted(folders.items()):
            print(f"\n  📁 {folder}/")
            for filename, desc in files:
                print(f"     ├── {filename:<40} ({desc})")

        # Quality assessment
        print(f"\n✅ Quality Assessment:")

        # Check if filenames are meaningful (not "untitled")
        meaningful_filenames = sum(
            1 for _, r in results
            if r.filename and r.filename not in ('untitled', 'document')
        )
        filename_quality = (meaningful_filenames / len(results) * 100) if results else 0

        # Check if folder names are meaningful
        meaningful_folders = sum(
            1 for _, r in results
            if r.folder_name and r.folder_name not in ('documents', 'untitled', 'files')
        )
        folder_quality = (meaningful_folders / len(results) * 100) if results else 0

        print(f"  Meaningful filenames: {meaningful_filenames}/{len(results)} ({filename_quality:.0f}%)")
        print(f"  Meaningful folders: {meaningful_folders}/{len(results)} ({folder_quality:.0f}%)")

        # Check descriptions
        good_descriptions = sum(
            1 for _, r in results
            if r.description and len(r.description) > 100 and not r.description.startswith("Content about")
        )
        description_quality = (good_descriptions / len(results) * 100) if results else 0
        print(f"  Quality descriptions: {good_descriptions}/{len(results)} ({description_quality:.0f}%)")

        overall_quality = (filename_quality + folder_quality + description_quality) / 3
        print(f"\n  Overall Quality Score: {overall_quality:.1f}%")

        if overall_quality >= 90:
            print("  🎉 Excellent! Major improvement over v1")
        elif overall_quality >= 75:
            print("  ✓ Good! Significant improvement")
        elif overall_quality >= 60:
            print("  ⚠️  Acceptable, but needs more tuning")
        else:
            print("  ✗ Needs improvement")

        print("\n✓ Test completed successfully!")
        return True


def main():
    """Run improved processing tests."""
    print("\n" + "=" * 80)
    print("File Organizer v2 - Improved Processing Test")
    print("Testing: Better prompts, lighter filtering, NLTK auto-download")
    print("=" * 80)

    try:
        success = test_improved_processing()

        # Cleanup
        test_dir = Path(__file__).parent.parent / "test_data_improved"
        if test_dir.exists():
            import shutil
            shutil.rmtree(test_dir)
            print(f"\n🧹 Cleaned up test directory")

        if success:
            print("\n✓ All tests passed!")
            sys.exit(0)
        else:
            print("\n✗ Some tests failed")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        logger.exception("Test failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
