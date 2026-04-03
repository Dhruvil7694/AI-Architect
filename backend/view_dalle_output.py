"""
Simple viewer to display the generated DALL-E floor plan image.
"""
import sys
from pathlib import Path

try:
    from PIL import Image
    import matplotlib.pyplot as plt
except ImportError:
    print("Installing required packages...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pillow", "matplotlib"])
    from PIL import Image
    import matplotlib.pyplot as plt


def main():
    """Display the generated floor plan image."""
    output_dir = Path(__file__).parent / "output"
    image_file = output_dir / "dalle_floor_plan.png"
    
    if not image_file.exists():
        print(f"Error: Image not found at {image_file}")
        print("Run test_dalle_floor_plan.py first to generate the image.")
        return
    
    print(f"Opening image: {image_file}")
    
    # Load and display image
    img = Image.open(image_file)
    
    # Create figure
    plt.figure(figsize=(16, 9))
    plt.imshow(img)
    plt.axis('off')
    plt.title('DALL-E Generated Floor Plan (Enhanced Prompt)', fontsize=16, pad=20)
    plt.tight_layout()
    
    print(f"Image size: {img.size[0]} x {img.size[1]} pixels")
    print(f"Image mode: {img.mode}")
    print("\nDisplaying image... (close window to exit)")
    
    plt.show()


if __name__ == "__main__":
    main()
