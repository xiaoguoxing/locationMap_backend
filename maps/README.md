# Location Mapper: Water Quality Visualization Tool

## Overview

Location Mapper is an advanced Python script that generates interactive maps from water quality monitoring CSV data. It now supports two map visualization modes:

1. **Detailed Point Maps**: Individual sampling locations with color-coded markers
2. **District-Level Choropleth Maps**: Aggregated water quality data by Hong Kong districts

## Features

### Detailed Point Maps
- Color-coded markers for each sampling location
- Interactive popups with detailed sample information
- Supports chlorine, E. coli, and turbidity parameters

### District Choropleth Maps
- Aggregated water quality data for Hong Kong's 18 districts
- Color-coded districts based on water quality metrics
- Easy-to-understand regional overview
- Supports chlorine, E. coli, and turbidity parameters

## Installation Requirements

- Python 3.8+
- Required libraries:
  * pandas
  * folium
  * geopandas
  * numpy

## Usage

### Basic Command

```bash
python maps/location_mapper.py
```

### Advanced Usage with Mode Selection

```bash
# Generate both detailed and district maps (default)
python maps/location_mapper.py --mode both

# Generate only detailed point maps
python maps/location_mapper.py --mode detailed

# Generate only district choropleth maps
python maps/location_mapper.py --mode district
```

## Output Directories

- **Detailed Maps**: `maps/output/detailed/`
- **District Maps**: `maps/output/district/`

## Color Coding & Legend

### Residual Chlorine (mg/L)
- 🔴 Red (opacity 0.7): < 0.2 — Insufficient
- 🟢 Green: 0.2 - 1.5 — Satisfactory
- 🟠 Orange: 1.6 - 2.0 — Slightly High
- 🔴 Dark Red: 2.1 - 3.0 — High
- 🔴 Red: > 3.0 — Very High

### E. coli (cfu/100mL)
- 🟢 Green: 0 — Satisfactory
- 🔴 Red: Any value > 0 — Unsatisfactory

### Turbidity (NTU)
- 🟢 Green: ≤ 1.5 — Satisfactory
- 🟠 Orange: 1.6 - 3.0 — Slightly High
- 🔴 Dark Red: 3.1 - 10.0 — High
- 🔴 Red: > 10.0 — Very High

## Aggregation Methods

### Chlorine and Turbidity
- **Mean**: Average of all readings in the district
- **Max**: Highest value in the district

### E. coli
- **Contamination Rate**: Percentage of samples with E. coli present

## Troubleshooting

- Ensure input CSV files are in `gencsv/output/` directory
- Check that required columns exist: `loc_gps_latitude`, `loc_gps_longitude`, `result`, `district`
- Verify Python and library versions

## Contributing

Contributions are welcome! Please submit pull requests or open issues on the project repository.

## License

[Insert your project's license here]

## Contact

[Insert contact information or support details]
