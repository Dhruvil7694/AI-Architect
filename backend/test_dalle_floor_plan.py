"""
Test script for DALL-E floor plan generation with enhanced prompt.
Generates a sample 2BHK floor plan image and saves it to output folder.
"""
import os
import sys
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from services.floor_plan_image_prompt import build_architectural_prompt
from ai_layer.image_client import generate_image


def create_sample_layout():
    """Create a sample 2BHK layout for testing."""
    return {
        "units": [
            {
                "id": "U1",
                "type": "2BHK",
                "side": "south",
                "x": 0.0,
                "y": 0.0,
                "w": 12.0,
                "h": 6.0,
                "rooms": [
                    {"id": "U1_R1", "type": "FOYER", "x": 0.5, "y": 5.0, "w": 1.8, "h": 1.0},
                    {"id": "U1_R2", "type": "LIVING", "x": 2.5, "y": 3.5, "w": 4.5, "h": 3.8},
                    {"id": "U1_R3", "type": "KITCHEN", "x": 7.2, "y": 4.0, "w": 3.0, "h": 2.5},
                    {"id": "U1_R4", "type": "BEDROOM", "x": 0.5, "y": 0.5, "w": 3.5, "h": 3.0},
                    {"id": "U1_R5", "type": "BATHROOM", "x": 4.2, "y": 0.5, "w": 2.0, "h": 1.8},
                    {"id": "U1_R6", "type": "BEDROOM", "x": 6.5, "y": 0.5, "w": 3.0, "h": 2.7},
                    {"id": "U1_R7", "type": "TOILET", "x": 9.7, "y": 0.5, "w": 1.5, "h": 1.8},
                    {"id": "U1_R8", "type": "PASSAGE", "x": 0.5, "y": 3.5, "w": 1.5, "h": 1.5},
                    {"id": "U1_R9", "type": "BALCONY", "x": 2.5, "y": 0.0, "w": 3.0, "h": 1.5},
                ]
            },
            {
                "id": "U2",
                "type": "2BHK",
                "side": "north",
                "x": 12.0,
                "y": 0.0,
                "w": 12.0,
                "h": 6.0,
                "rooms": [
                    {"id": "U2_R1", "type": "FOYER", "x": 12.5, "y": 5.0, "w": 1.8, "h": 1.0},
                    {"id": "U2_R2", "type": "LIVING", "x": 14.5, "y": 3.5, "w": 4.5, "h": 3.8},
                    {"id": "U2_R3", "type": "KITCHEN", "x": 19.2, "y": 4.0, "w": 3.0, "h": 2.5},
                    {"id": "U2_R4", "type": "BEDROOM", "x": 12.5, "y": 0.5, "w": 3.5, "h": 3.0},
                    {"id": "U2_R5", "type": "BATHROOM", "x": 16.2, "y": 0.5, "w": 2.0, "h": 1.8},
                    {"id": "U2_R6", "type": "BEDROOM", "x": 18.5, "y": 0.5, "w": 3.0, "h": 2.7},
                    {"id": "U2_R7", "type": "TOILET", "x": 21.7, "y": 0.5, "w": 1.5, "h": 1.8},
                    {"id": "U2_R8", "type": "PASSAGE", "x": 12.5, "y": 3.5, "w": 1.5, "h": 1.5},
                    {"id": "U2_R9", "type": "BALCONY", "x": 14.5, "y": 0.0, "w": 3.0, "h": 1.5},
                ]
            }
        ]
    }


def create_sample_metrics():
    """Create sample metrics for a typical residential floor."""
    return {
        "floorLengthM": 24.0,
        "floorWidthM": 12.0,
        "floorDepthM": 12.0,
        "nUnitsPerFloor": 2,
        "nFloors": 10,
        "storeyHeightM": 3.0,
        "buildingHeightM": 30.0,
        "efficiencyPct": 75.0,
        "netBuaSqm": 180.0,
        "nLifts": 1,
        "nStairs": 1,
    }


def main():
    """Generate floor plan image using DALL-E."""
    print("=" * 80)
    print("DALL-E Floor Plan Generation Test")
    print("=" * 80)
    
    # Create sample data
    layout = create_sample_layout()
    metrics = create_sample_metrics()
    
    print("\n[1/4] Building enhanced architectural prompt...")
    prompt = build_architectural_prompt(
        layout=layout,
        metrics=metrics,
        segment="mid",
        units_per_core=2,
        building_height_m=30.0
    )
    
    print(f"\n[2/4] Prompt generated ({len(prompt)} characters)")
    print("\n" + "─" * 80)
    print("PROMPT PREVIEW:")
    print("─" * 80)
    print(prompt[:1000] + "\n... (truncated)\n")
    
    # Save full prompt to file
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    
    prompt_file = output_dir / "dalle_prompt.txt"
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)
    print(f"✓ Full prompt saved to: {prompt_file}")
    
    # Generate image
    print("\n[3/4] Generating image via DALL-E 3...")
    print("(This may take 20-30 seconds...)")
    
    try:
        image_base64 = generate_image(
            prompt=prompt,
            size="1792x1024",  # Landscape format for floor plans
            quality="hd",
            style="natural"
        )
        
        if image_base64:
            print("✓ Image generated successfully!")
            
            # Save image
            print("\n[4/4] Saving image...")
            import base64
            
            image_file = output_dir / "dalle_floor_plan.png"
            image_bytes = base64.b64decode(image_base64)
            
            with open(image_file, "wb") as f:
                f.write(image_bytes)
            
            print(f"✓ Image saved to: {image_file}")
            print(f"  Size: {len(image_bytes) / 1024:.1f} KB")
            
            # Also save metadata
            metadata = {
                "prompt_length": len(prompt),
                "layout": {
                    "units": len(layout["units"]),
                    "unit_types": [u["type"] for u in layout["units"]]
                },
                "metrics": metrics,
                "dalle_params": {
                    "size": "1792x1024",
                    "quality": "hd",
                    "style": "natural"
                }
            }
            
            metadata_file = output_dir / "dalle_metadata.json"
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
            
            print(f"✓ Metadata saved to: {metadata_file}")
            
            print("\n" + "=" * 80)
            print("SUCCESS! Floor plan image generated.")
            print("=" * 80)
            print(f"\nOutput files:")
            print(f"  - Image: {image_file}")
            print(f"  - Prompt: {prompt_file}")
            print(f"  - Metadata: {metadata_file}")
            
        else:
            print("✗ Image generation failed - no image returned")
            print("\nPossible reasons:")
            print("  - OPENAI_API_KEY not set in environment")
            print("  - API rate limit reached")
            print("  - Network connectivity issue")
            print("\nCheck backend/ai_layer/config.py for configuration")
            
    except Exception as e:
        print(f"✗ Error during image generation: {e}")
        import traceback
        traceback.print_exc()
        
        print("\nTroubleshooting:")
        print("  1. Ensure OPENAI_API_KEY is set in your environment")
        print("  2. Check your OpenAI account has API credits")
        print("  3. Verify network connectivity")
        print("  4. Review the full prompt in: output/dalle_prompt.txt")


if __name__ == "__main__":
    main()
