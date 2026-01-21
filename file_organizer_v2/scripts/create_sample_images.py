#!/usr/bin/env python3
"""Create sample images for testing vision processing."""

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("Warning: Pillow not installed. Install with: pip install Pillow")
    sys.exit(1)


def create_sample_images(output_dir: Path) -> None:
    """Create sample images for testing.

    Args:
        output_dir: Directory to save images
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Sample 1: Landscape (nature scene)
    img1 = Image.new('RGB', (800, 600), color=(135, 206, 235))  # Sky blue
    draw = ImageDraw.Draw(img1)
    # Draw mountains (green triangles)
    draw.polygon([(0, 400), (300, 200), (600, 400)], fill=(34, 139, 34))
    draw.polygon([(400, 400), (500, 250), (700, 400)], fill=(60, 179, 113))
    # Draw sun
    draw.ellipse([650, 50, 750, 150], fill=(255, 255, 0))
    img1.save(output_dir / "mountain_landscape.jpg")
    print(f"✓ Created: mountain_landscape.jpg")

    # Sample 2: Abstract geometric
    img2 = Image.new('RGB', (600, 600), color=(255, 255, 255))
    draw = ImageDraw.Draw(img2)
    draw.rectangle([100, 100, 300, 300], fill=(255, 0, 0))
    draw.ellipse([300, 200, 500, 400], fill=(0, 0, 255))
    draw.polygon([(250, 50), (150, 200), (350, 200)], fill=(255, 255, 0))
    img2.save(output_dir / "geometric_shapes.jpg")
    print(f"✓ Created: geometric_shapes.jpg")

    # Sample 3: Simple text image
    img3 = Image.new('RGB', (800, 400), color=(240, 240, 240))
    draw = ImageDraw.Draw(img3)
    # Try to use a font, fallback to default if not available
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 60)
    except:
        font = ImageFont.load_default()
    draw.text((150, 150), "Hello World!", fill=(0, 0, 0), font=font)
    img3.save(output_dir / "text_hello_world.jpg")
    print(f"✓ Created: text_hello_world.jpg")

    # Sample 4: Food-like image (pizza-ish)
    img4 = Image.new('RGB', (600, 600), color=(255, 228, 196))  # Bisque
    draw = ImageDraw.Draw(img4)
    draw.ellipse([50, 50, 550, 550], fill=(255, 140, 0))  # Orange (pizza base)
    # Add toppings (red circles)
    for x, y in [(200, 200), (400, 200), (300, 350), (150, 400), (450, 400)]:
        draw.ellipse([x-30, y-30, x+30, y+30], fill=(220, 20, 60))
    img4.save(output_dir / "food_pizza.jpg")
    print(f"✓ Created: food_pizza.jpg")

    # Sample 5: Architecture-like (building)
    img5 = Image.new('RGB', (600, 800), color=(135, 206, 235))  # Sky
    draw = ImageDraw.Draw(img5)
    # Building
    draw.rectangle([150, 300, 450, 700], fill=(169, 169, 169))
    # Windows (3x4 grid)
    for row in range(4):
        for col in range(3):
            x = 200 + col * 80
            y = 350 + row * 80
            draw.rectangle([x, y, x+50, y+60], fill=(255, 255, 200))
    img5.save(output_dir / "urban_building.jpg")
    print(f"✓ Created: urban_building.jpg")

    print(f"\n✓ Created 5 sample images in {output_dir}")


if __name__ == "__main__":
    output_dir = Path("demo_images")
    create_sample_images(output_dir)
