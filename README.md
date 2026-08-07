# Location Map - Water Quality Dashboard

HK Water Quality Data Visualization Dashboard for chlorination, E. coli, and turbidity monitoring.

## Quick Start

### Option 1: Run All in One Batch
```cmd
run_all.bat
```

### Option 2: Run Individual Batch Files
```cmd
REM Step 1: Generate CSV from database
01_extract_csv.bat

REM Step 2: Generate district and detailed maps
02_generate_maps.bat

REM Step 3: Start the dashboard
03_start_dashboard.bat
```

## Full Workflow (Manual)

### 1. Extract CSV Data from Database
```cmd
cd c:\develop\workspace\locationmap
python gencsv/main.py
```

**Output:** `gencsv/output/*.csv` files grouped by date ranges.

**Parameters extracted:**
- `cl2_free_1` - Free Chlorine (mg/L)
- `ecoli` - E. coli (CFU/100mL)
- `turby` - Turbidity (NTU)

### 2. Generate District + Detailed Maps
```cmd
cd c:\develop\workspace\locationmap
python maps/location_mapper.py
```

**Output directories:**
- `maps/output/district/*.html` - District choropleth maps with value labels at district centroids
- `maps/output/detailed/*.html` - Sample point location maps with circle markers

### 3. Generate Multi-Parameter Combined Maps
```cmd
cd c:\develop\workspace\locationmap
python maps/multi_param_mapper.py
```

**Output directory:**
- `maps/output/district_all_param/*.html` - Combined choropleth maps showing all 3 parameters per district

### 4. Start the Dashboard
```cmd
cd c:\develop\workspace\locationmap\dashboard
python app.py
```

Then browse to: **http://localhost:5000**

---

## Color Legend (Water Quality Standards)

### Free Chlorine (Cl₂)
| Color | Range (mg/L) | Meaning |
|-------|--------------|---------|
| 🔴 Red | < 0.2 | Insufficient residual disinfection |
| 🟢 Green | 0.2 - 1.5 | Ideal range (WSD standard) |
| 🟠 Orange | 1.5 - 2.0 | Slightly elevated |
| 🔴 Red | > 2.0 | Excessive chlorine |

### E. coli Contamination Rate
| Color | Range | Meaning |
|-------|-------|---------|
| 🟢 Green | 0% | No contamination detected |
| 🟠 Orange | ≤ 10% | Low contamination |
| 🔴 Red | > 10% | High contamination |

### Turbidity
| Color | Range (NTU) | Meaning |
|-------|--------------|---------|
| 🟢 Green | ≤ 1.5 | Acceptable |
| 🟠 Orange | 1.6 - 3.0 | Slightly cloudy |
| 🔴 Red | > 3.0 | Cloudy/turbid |

---

## Project Structure

```
locationmap/
├── README.md                      # This file
├── run_all.bat                    # One-click run everything
├── 01_extract_csv.bat            # Step 1: DB to CSV
├── 02_generate_maps.bat          # Step 2: All maps
├── 03_start_dashboard.bat        # Step 3: Web dashboard
│
├── gencsv/                       # Data extraction module
│   ├── main.py                   # Main entry point
│   ├── setting.ini               # DB connection settings
│   └── output/                   # Generated CSV files
│
├── maps/                         # Map generation module
│   ├── choropleth_mapper.py      # Choropleth legend + centroid logic
│   ├── district_aggregator.py    # Color logic + district aggregation
│   ├── location_mapper.py         # Single-param maps (district + detailed)
│   ├── multi_param_mapper.py      # Multi-param combined maps
│   ├── data/
│   │   ├── hk_districts.geojson   # District boundaries
│   │   └── district_mapping.py    # Name normalization
│   └── output/
│       ├── district/              # District choropleth maps
│       ├── detailed/              # Detailed location pin maps
│       └── district_all_param/    # Multi-param combined maps
│
└── dashboard/                    # Flask web dashboard
    ├── app.py                     # Flask application
    ├── templates/
    └── static/
        ├── css/
        └── js/
```

---

## Recent Updates (2026-05-02)

### Bug Fixes and Improvements:

1. **Dashboard now shows all 3 map directories**
   - Fixed: `scan_maps_directory()` only scanned 2 of 3 output directories
   - Now includes: `district/`, `district_all_param/`, and `detailed/`

2. **Fixed district value label positioning**
   - Old: Simple vertex averaging skewed by duplicate closing vertices
   - New: **Shoelace formula** for true geometric centroid calculation
   - Also handles `MultiPolygon` geometries (Islands district) with area-weighted averaging

3. **Legend style unified**
   - Single-param maps now use same compact bottom-left legend as multi-param maps

4. **Free Chlorine color logic fixed**
   - **Bug fixed:** Gap at 1.5-1.6 fell to RED
   - **Fixed to:** `1.5 < value ≤ 2.0` = ORANGE (continuous)
   - Confirmed: `<0.2` = RED (insufficient disinfection)

5. **Legend updated to show all red zones**
   - **Before:** `🟢 0.2–1.5  🟠 1.6–2.0  🔴 >2.0`
   - **After:**  `🔴 <0.2  🟢 0.2–1.5  🟠 1.5–2.0  🔴 >2.0`
