## 10m × 10m Area Accounting Truth Table

This document freezes a concrete geometric example that all Phase 1
area-accounting logic must reproduce. It defines **explicit coordinates**
and **numeric areas** for footprint, walls, core, corridor, unit, rooms,
and RERA carpet.

### 1. Geometry Conventions

- Coordinates in metres, local slab frame.
- `footprint_polygon` is the **gross built-up boundary** at the **outer
  face of external walls**.
- External walls are modelled as a continuous ring of thickness
  `t_ext = 0.20 m` **inside** the footprint.
- The internal free slab (inside external walls) is the rectangle from
  `(0.20, 0.20)` to `(9.80, 9.80)`.
- Core, corridor, and unit zones lie entirely inside this internal
  slab and do **not** overlap the external wall ring.
- Internal partitions are modelled as separate wall polygons of
  thickness `t_int = 0.10 m`; room polygons do **not** include wall
  thickness.

### 2. Base Rectangles (Coordinates)

- **Footprint (gross built-up)**
  - Outer rectangle: `(0.0, 0.0)` to `(10.0, 10.0)`
  - Width = 10.0 m, Depth = 10.0 m

- **Internal slab (inside external walls)**
  - Inner rectangle: `(0.20, 0.20)` to `(9.80, 9.80)`
  - Width = 9.60 m, Depth = 9.60 m

- **Core rectangle**
  - `(0.20, 0.20)` to `(3.20, 4.20)`
  - Width = 3.0 m, Depth = 4.0 m

- **Corridor rectangle**
  - `(3.20, 0.20)` to `(9.80, 1.40)`
  - Width = 6.60 m, Depth = 1.20 m

- **Unit slab (single residential unit)**
  - `(3.20, 1.40)` to `(9.80, 9.80)`
  - Width = 6.60 m, Depth = 8.40 m

### 3. Room and Internal Wall Geometry (Inside Unit)

Within the unit slab `(3.20, 1.40)` to `(9.80, 9.80)`:

- **Partition wall (between two rooms)**
  - Thickness `t_int = 0.10 m`
  - Polygon: `(3.20, 5.55)` to `(9.80, 5.65)`
  - Width = 6.60 m, Height = 0.10 m

- **Bedroom polygon**
  - `(3.20, 1.40)` to `(9.80, 5.55)`
  - Width = 6.60 m, Height = 4.15 m

- **Living room polygon**
  - `(3.20, 5.65)` to `(9.80, 9.80)`
  - Width = 6.60 m, Height = 4.15 m

Rooms do **not** overlap the internal partition wall polygon; there is
an intentional 0.10 m gap between the bedroom and living rectangles
equal to the wall thickness.

### 4. Manually Computed Areas (sq.m)

All areas below are exact analytical values from the rectangles above.

#### 4.1 Gross and External Walls

- **Gross built-up area (footprint)**
  - `gross_built_up_sqm = 10.0 × 10.0 = 100.00`

- **Internal slab area (inside external walls)**
  - `A_inner = 9.60 × 9.60 = 92.16`

- **External wall ring area**
  - `external_wall_area_sqm = gross_built_up_sqm − A_inner`
  - `= 100.00 − 92.16`
  - `= 7.84`

#### 4.2 Core, Corridor, Unit Envelope

- **Core area**
  - `core_area_sqm = 3.0 × 4.0 = 12.00`

- **Corridor area**
  - `corridor_area_sqm = 6.60 × 1.20 = 7.92`

- **Unit envelope (unit slab) area**
  - `unit_envelope_area_sqm = 6.60 × 8.40 = 55.44`

- **Check: interior slab partition**
  - `core_area_sqm + corridor_area_sqm + unit_envelope_area_sqm`
  - `= 12.00 + 7.92 + 55.44 = 75.36`
  - Interior residual (other common/void) inside internal slab:
  - `A_inner − 75.36 = 92.16 − 75.36 = 16.80`

For Phase 1, `common_area_total_sqm` will be defined as:

```text
common_area_total_sqm = core_area_sqm + corridor_area_sqm + shaft_area_sqm
                       = 12.00 + 7.92 + 0.00
                       = 19.92
```

#### 4.3 Internal Rooms and Internal Wall

- **Bedroom area**
  - Width = 6.60, Height = 4.15
  - `bedroom_area_sqm = 6.60 × 4.15 = 27.39`

- **Living room area**
  - Same dimensions as bedroom
  - `living_area_sqm = 6.60 × 4.15 = 27.39`

- **Total internal room area**
  - `room_internal_area_total_sqm = 27.39 + 27.39 = 54.78`

- **Internal partition wall area**
  - Width = 6.60, Thickness = 0.10
  - `internal_wall_area_sqm = 6.60 × 0.10 = 0.66`

#### 4.4 RERA Carpet and Shared Wall Allocation

This example has **one unit only**; the internal partition is between
two rooms of the **same unit**, and there are no walls shared between
two different units.

- **Shared wall allocation**
  - For this truth-table: `shared_wall_allocation_sqm = 0.00`
    (no inter-unit shared walls).

- **RERA carpet per unit**

Using the Phase 1 convention:

```text
RERA carpet =
    sum(room internal areas)
  + internal partition wall thickness contributions
  - external wall thickness (0 here)
  - common wall share (0 here)
```

For this example:

- `sum(room internal areas) = 54.78`
- `internal partition wall contribution = internal_wall_area_sqm = 0.66`
- `external wall thickness contribution = 0.00`
- `common wall share = 0.00`

Therefore:

```text
rera_carpet_area_total_sqm = 54.78 + 0.66 = 55.44
carpet_per_unit = [55.44]  # single unit
```

Note that:

```text
rera_carpet_area_total_sqm == unit_envelope_area_sqm == 55.44
```

in this particular configuration, because rooms plus the single internal
partition exactly fill the unit slab.

#### 4.5 Efficiency Ratios

- **Floor efficiency ratio (unit envelope vs gross)**

```text
efficiency_ratio = unit_envelope_area_sqm / gross_built_up_sqm
                 = 55.44 / 100.00
                 = 0.5544
```

- **Common area percentage**

```text
common_area_percentage = common_area_total_sqm / gross_built_up_sqm
                       = 19.92 / 100.00
                       = 0.1992   # 19.92%
```

- **Carpet-to-BUA ratio**

```text
carpet_to_bua_ratio = rera_carpet_area_total_sqm / gross_built_up_sqm
                     = 55.44 / 100.00
                     = 0.5544
```

- **Room-to-unit-envelope ratio (internal room floor vs unit slab)**

```text
room_to_envelope_ratio = room_internal_area_total_sqm / unit_envelope_area_sqm
                        = 54.78 / 55.44
                        ≈ 0.9881
```

These numeric values are the **truth-table constants**. Phase 1
area-accounting implementations must reproduce them (within a small
numeric tolerance) when given the exact same geometry.

