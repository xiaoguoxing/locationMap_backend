# District-Level Choropleth Map Implementation Plan

## Overview
This plan details the implementation of district-level choropleth maps to replace the current GPS point-based maps, while preserving the detailed view capability for future use.

## Architecture

### Current Flow
```
CSV Data → GPS Points → Individual Markers on OpenStreetMap
```

### New Flow
```
CSV Data → Aggregate by District → Choropleth Colors on District Boundaries
                    ↓
         Detailed GPS Points (saved separately)
```

## Components

### 1. District Boundary Data (GeoJSON)
- **Source**: Hong Kong 18 Districts boundary data
- **Format**: GeoJSON with district names matching your data's `district` column
- **File**: `maps/data/hk_districts.geojson`

### 2. Data Aggregation Module (`district_aggregator.py`)
```python
Functions:
- aggregate_by_district(df, parameter_name) → district_stats
- calculate_statistics(values, parameter_name) → stats dict
- match_district_names(district_names, geojson_names) → mapping
```

### 3. Choropleth Mapper (`choropleth_mapper.py`)
```python
Functions:
- create_choropleth_map(district_stats, geojson_path, output_path)
- generate_color_scale(parameter_name, min_val, max_val)
- add_legend(map_obj, parameter_name, color_scale)
```

### 4. Modified Main Script (`location_mapper.py`)
Changes:
- Accept `--mode` argument: `detailed`, `district`, or `both`
- Output to separate directories:
  - `maps/output/detailed/` - Current GPS point maps
  - `maps/output/district/` - New choropleth maps

## Directory Structure
```
maps/
├── location_mapper.py          # Modified main script
├── district_aggregator.py      # New: Data aggregation
├── choropleth_mapper.py        # New: Choropleth generation
├── data/
│   └── hk_districts.geojson    # New: District boundaries
├── output/
│   ├── detailed/               # New: GPS point maps
│   └── district/               # New: Choropleth maps
└── README.md                   # Updated documentation
```

## Color Schemes by Parameter

### Chlorine (cl2_free_1)
- Green: 0.2-1.5 mg/L (safe)
- Orange: 1.6-2.0 mg/L (warning)
- Red: >2.0 mg/L (alert)
- Gray: No data

### E. coli (ecoli)
- Green: 0 CFU/100mL (safe)
- Red: >0 CFU/100mL (contaminated)
- Gray: No data

### Turbidity (turby)
- Green: ≤1.5 NTU (clear)
- Orange: 1.6-3.0 NTU (slightly cloudy)
- Red: >3.0 NTU (cloudy)
- Gray: No data

## Aggregation Methods

### For Chlorine and Turbidity (continuous values)
- **Primary**: Mean (average) of all readings in district
- **Secondary**: Maximum value (for worst-case view)

### For E. coli (binary presence/absence)
- **Primary**: Percentage of samples with E. coli present
- **Secondary**: Count of contaminated samples

## Implementation Phases

### Phase 1: Foundation
1. Source Hong Kong district boundary GeoJSON
2. Create `district_aggregator.py`
3. Test aggregation with sample data

### Phase 2: Choropleth Generation
1. Create `choropleth_mapper.py`
2. Implement color scales for each parameter
3. Test choropleth generation

### Phase 3: Integration
1. Modify `location_mapper.py` for dual output
2. Update directory structure
3. Test both map types generation

### Phase 4: Documentation
1. Update README with new features
2. Add usage examples
3. Document color schemes and aggregation methods

## Next Steps

1. **Source the GeoJSON data** for Hong Kong 18 districts
2. **Review and approve this plan**
3. **Decide on aggregation method** (mean vs max for chlorine/turbidity)
4. **Begin Phase 1 implementation**

Would you like me to proceed with sourcing the Hong Kong district boundary data and beginning implementation?