# DALL-E Floor Plan Prompt Improvements

## Summary

Successfully enhanced the floor plan image generation prompt with detailed connectivity rules, measurement specifications, and architectural standards. The improved prompt generates professional CAD-style floor plans with clear spatial relationships.

## What Was Changed

### File Modified
- `backend/services/floor_plan_image_prompt.py` - Enhanced `build_architectural_prompt()` function

### Key Improvements

#### 1. **Spatial Connectivity Rules** (NEW)
Added explicit flow descriptions for each unit type:
- **1BHK**: Entry → Foyer → Living (with balcony) | Kitchen adjacent | Bedroom with bathroom
- **2BHK**: Entry → Foyer → Living (balcony) → Kitchen | Passage → Master BR (attached bath) + BR2 | Powder room
- **3BHK**: Entry → Foyer → Living+Dining (balcony) → Kitchen | Passage → 2 Master BRs (baths) + BR3 | Common WC
- **4BHK**: Entry → Living → Dining (balcony) → Kitchen | Passage → 2 Master BRs (baths) + 2 BRs | Common WC

#### 2. **Enhanced Room Specifications**
- Added area calculations (sqm) for every room
- Format: `ROOM_NAME width×depth (area sqm)`
- Example: `LR 4.5×3.8m (17.1sqm)`

#### 3. **Detailed Labeling Requirements**
```
Every room must have centered label showing:
  * Room name (e.g., LIVING ROOM, MASTER BEDROOM, KITCHEN)
  * Dimensions in format: width × depth (e.g., 4.5m × 3.8m)
  * Area in square meters (e.g., 17.1sqm)
Label format: 'LIVING ROOM\n4.5m × 3.8m\n17.1sqm'
```

#### 4. **Architectural Standards**
- Wall thickness specifications (230mm exterior, 115mm interior)
- Door width minimums (900mm main, 750mm bedroom, 600mm bathroom)
- Symbol conventions (doors, windows, stairs, lifts, balconies)
- Professional CAD drawing style requirements

#### 5. **Connectivity Rules**
- Habitable rooms on exterior walls with windows
- Kitchen adjacent to living/dining
- Balconies from living room and/or master bedroom
- Master bedrooms with attached bathrooms on interior side
- Common toilet near living area (not bedroom zone)
- Passage connects living to bedroom zone
- Wet zones clustered for plumbing efficiency

#### 6. **Quality Standards**
- No landlocked spaces
- Clear circulation paths
- Professional presentation quality
- Readable text labels with font hierarchy
- Clean white background with black linework only

## Test Results

### Generated Files
```
backend/output/
├── dalle_floor_plan.png      (1,089 KB - 1792×1024 HD image)
├── dalle_prompt.txt           (3,969 chars - full prompt)
└── dalle_metadata.json        (516 bytes - generation metadata)
```

### Test Configuration
- **Layout**: 2 units × 2BHK
- **Floor Plate**: 24.0m × 12.0m (288 sqm)
- **Building**: 10 floors, 30m height
- **DALL-E Settings**: 1792×1024, HD quality, natural style

### Prompt Statistics
- **Length**: 3,872 characters
- **Sections**: 9 major sections
- **Connectivity Rules**: 7 explicit rules
- **Room Details**: Full specifications for all 9 rooms per unit

## How to Use

### 1. Generate a Floor Plan Image

```bash
cd backend
python test_dalle_floor_plan.py
```

This will:
- Build the enhanced prompt
- Call DALL-E 3 API
- Save image to `output/dalle_floor_plan.png`
- Save prompt to `output/dalle_prompt.txt`
- Save metadata to `output/dalle_metadata.json`

### 2. View the Generated Image

```bash
python view_dalle_output.py
```

### 3. Integrate with Existing Pipeline

The enhanced prompt is automatically used by:
- `backend/services/ai_floor_plan_service.py` (line 269)
- Called via `_generate_images_for_model()` function
- Supports multiple image models: DALL-E 3, Gemini Imagen, Recraft, etc.

## Prompt Structure

```
1. STYLE ANCHOR
   └─ Professional CAD drawing style, black on white, no 3D

2. FLOOR PLATE DIMENSIONS
   └─ Exact measurements, wall thicknesses, geometry rules

3. LAYOUT ORGANIZATION
   └─ Core placement, corridor structure, unit arrangement

4. SPATIAL CONNECTIVITY ⭐ NEW
   └─ Unit-by-unit flow descriptions with explicit connections

5. CONNECTIVITY RULES ⭐ NEW
   └─ 7 mandatory spatial relationship rules

6. ROOM SPECIFICATIONS ⭐ ENHANCED
   └─ Every room with dimensions and area calculations

7. ARCHITECTURAL SYMBOLS
   └─ Standard CAD conventions for doors, windows, stairs, lifts

8. LABELING REQUIREMENTS ⭐ ENHANCED
   └─ Detailed format specifications with examples

9. QUALITY STANDARDS ⭐ NEW
   └─ Professional presentation requirements

10. FINAL CONSTRAINTS
    └─ Technical drawing constraints and exclusions
```

## Key Improvements for DALL-E

### What Works Well
✅ Explicit connectivity descriptions ("Entry → Foyer → Living")
✅ Room-by-room specifications with measurements
✅ Clear architectural symbol definitions
✅ Professional style anchoring (CAD drawing, black on white)
✅ Negative constraints (no furniture, no 3D, no colors)

### What to Watch For
⚠️ DALL-E may not get exact measurements (focus on proportions)
⚠️ Label placement might vary (centered vs. corner)
⚠️ Symbol accuracy depends on prompt clarity
⚠️ Complex layouts (4+ units) may need simplified prompts

## BHK-Specific Bathroom Rules

### 1BHK
- 1 common bathroom only
- No attached bathrooms

### 2BHK
- 1 master bedroom with attached bathroom
- 1 common toilet/powder room near living area

### 3BHK
- 2 master bedrooms (each with attached bathroom)
- 1 common toilet near living area

### 4BHK
- 2-3 bedrooms with attached bathrooms
- 1 common toilet near living area

## Configuration

### Environment Variables
```bash
# Required for DALL-E generation
OPENAI_API_KEY=sk-...

# Optional DALL-E settings (defaults shown)
DALLE_MODEL=dall-e-3
DALLE_SIZE=1792x1024
DALLE_QUALITY=hd
DALLE_TIMEOUT_S=30.0
FLOOR_PLAN_IMAGE_ENABLED=1
```

### API Settings
- **Model**: DALL-E 3
- **Size**: 1792×1024 (landscape, ideal for floor plans)
- **Quality**: HD (higher detail)
- **Style**: Natural (realistic architectural drawing)
- **Timeout**: 30 seconds

## Next Steps

### Recommended Enhancements
1. **Test with different unit types** (1BHK, 3BHK, 4BHK)
2. **Validate connectivity** in generated images
3. **Iterate on label formats** if text is unclear
4. **Add dimension lines** if measurements need emphasis
5. **Test with complex layouts** (4+ units per floor)

### Alternative Approaches
1. **Two-stage generation**: SVG → Image-to-image refinement
2. **Prompt templates**: Pre-built prompts for common layouts
3. **Post-processing**: Add labels/dimensions programmatically
4. **Hybrid approach**: DALL-E for aesthetics + SVG for precision

## Files Reference

### Modified
- `backend/services/floor_plan_image_prompt.py` - Enhanced prompt builder

### Created
- `backend/test_dalle_floor_plan.py` - Test script
- `backend/view_dalle_output.py` - Image viewer
- `backend/DALLE_PROMPT_IMPROVEMENTS.md` - This document

### Generated
- `backend/output/dalle_floor_plan.png` - Sample image
- `backend/output/dalle_prompt.txt` - Full prompt
- `backend/output/dalle_metadata.json` - Generation metadata

## Troubleshooting

### Image Not Generated
1. Check `OPENAI_API_KEY` is set in environment
2. Verify OpenAI account has API credits
3. Check network connectivity
4. Review error messages in console output

### Poor Image Quality
1. Increase prompt specificity for problem areas
2. Try different DALL-E sizes (1024×1024, 1792×1024)
3. Adjust quality setting (standard vs. HD)
4. Simplify complex layouts

### Incorrect Connectivity
1. Review connectivity descriptions in prompt
2. Add more explicit spatial relationships
3. Use negative prompts to exclude unwanted features
4. Test with simpler layouts first

## Cost Considerations

### DALL-E 3 Pricing (as of 2024)
- **Standard (1024×1024)**: $0.040 per image
- **HD (1024×1024)**: $0.080 per image
- **HD (1792×1024)**: $0.120 per image

### Optimization Tips
- Use standard quality for testing
- Switch to HD for final production images
- Cache generated images to avoid regeneration
- Consider batch generation for multiple floors

---

**Status**: ✅ Successfully implemented and tested
**Date**: March 29, 2026
**Image Generated**: `backend/output/dalle_floor_plan.png` (1.06 MB)
