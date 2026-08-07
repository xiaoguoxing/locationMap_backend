## Summary: Markdown Files and Map API Functions

### All Markdown Files Found (10 total)

| # | File Path | Purpose |
|---|-----------|---------|
| 1 | [`README.md`](README.md) | Main project overview and quick start guide |
| 2 | [`maps/README.md`](maps/README.md) | Location Mapper documentation - water quality visualization tool |
| 3 | [`gencsv/DATE_RANGE_ARCHITECTURE.md`](gencsv/DATE_RANGE_ARCHITECTURE.md) | Date-range SQL template processing architecture |
| 4 | [`gencsv/PARAMETER_GUIDE.md`](gencsv/PARAMETER_GUIDE.md) | Date Range Runner parameter guide |
| 5 | [`plans/choropleth_explained.md`](plans/choropleth_explained.md) | Choropleth maps explained with visual comparisons |
| 6 | [`plans/district_choropleth_plan.md`](plans/district_choropleth_plan.md) | District choropleth implementation plan |
| 7 | [`plans/location_mapping_architecture.md`](plans/location_mapping_architecture.md) | Location mapping architecture design |
| 8 | [`plans/multi_param_district_map_plan.md`](plans/multi_param_district_map_plan.md) | Multi-parameter district map generation plan |
| 9 | [`plans/water_quality_dashboard_spec.md`](plans/water_quality_dashboard_spec.md) | Water quality dashboard specification |

---

### Map API Functions (Using Folium Library)

The project uses [**Folium**](https://python-visualization.github.io/folium/) (Python wrapper for Leaflet.js) for interactive map generation.

#### Core Map Creation Functions

| Function | File | Description |
|----------|------|-------------|
| [`folium.Map()`](maps/location_mapper.py:303) | location_mapper.py | Creates base map with OpenStreetMap tiles |
| [`folium.Map(location=[22.3193, 114.1694], zoom_start=10, tiles='CartoDB positron')`](maps/choropleth_mapper.py:232) | choropleth_mapper.py | Creates district choropleth map with CartoDB tiles |
| [`m.get_root().html.add_child(folium.Element(html))`](maps/choropleth_mapper.py:377) | choropleth_mapper.py | Adds custom HTML elements (title, legend) |

#### GeoJSON/District Layer Functions

| Function | File | Description |
|----------|------|-------------|
| [`folium.GeoJson()`](maps/choropleth_mapper.py:246) | choropleth_mapper.py | Renders GeoJSON district boundaries |
| [`folium.GeoJsonTooltip()`](maps/choropleth_mapper.py:253) | choropleth_mapper.py | Adds hover tooltips showing district info |
| [`folium.GeoJsonPopup()`](maps/choropleth_mapper.py:277) | choropleth_mapper.py | Adds click popups with detailed data |
| [`style_function(feature)`](maps/choropleth_mapper.py:234) | choropleth_mapper.py | Dynamic styling based on district values |
| [`highlight_function(feature)`](maps/choropleth_mapper.py:243) | choropleth_mapper.py | Hover highlight effect |

#### Point Marker Functions (Detailed Maps)

| Function | File | Description |
|----------|------|-------------|
| [`folium.CircleMarker()`](maps/location_mapper.py:345) | location_mapper.py | Creates color-coded sample point markers |
| [`folium.Marker()`](maps/choropleth_mapper.py:298) | choropleth_mapper.py | Adds value labels at district centroids |
| [`folium.DivIcon()`](maps/choropleth_mapper.py:300) | choropleth_mapper.py | Custom HTML icons for district labels |
| [`folium.Popup()`](maps/location_mapper.py:353) | location_mapper.py | Popup with sample details |
| [`folium.Tooltip()`](maps/location_mapper.py:354) | location_mapper.py | Hover tooltip with location info |

#### Data Processing Functions

| Function | File | Description |
|----------|------|-------------|
| [`aggregate_water_quality()`](maps/district_aggregator.py:97) | district_aggregator.py | Aggregates water quality data by district |
| [`get_color_for_district()`](maps/district_aggregator.py:175) | district_aggregator.py | Returns color based on parameter thresholds |
| [`load_district_mapping()`](maps/district_aggregator.py:19) | district_aggregator.py | Loads GeoJSON district name mappings |
| [`normalize_district_name()`](maps/district_aggregator.py:59) | district_aggregator.py | Normalizes district names for matching |
| [`calculate_polygon_centroid()`](maps/choropleth_mapper.py:65) | choropleth_mapper.py | Calculates geometric centroid for label placement |

#### Color Coding Functions

| Function | File | Description |
|----------|------|-------------|
| [`get_chlorine_color(value)`](maps/location_mapper.py:363) | location_mapper.py | Returns color for chlorine levels |
| [`get_ecoli_color(value)`](maps/location_mapper.py:384) | location_mapper.py | Returns color for E. coli levels |
| [`get_turby_color(value)`](maps/location_mapper.py:401) | location_mapper.py | Returns color for turbidity levels |

---

### Map Types Generated

| Map Type | Description | Output Directory |
|----------|-------------|------------------|
| **Detailed Point Maps** | Individual sampling locations with color-coded circle markers | `maps/output/detailed/` |
| **District Choropleth Maps** | HK 18 districts colored by aggregated water quality | `maps/output/district/` |
| **Multi-Parameter District Maps** | Combined map showing all 3 parameters per district | `maps/output/district_all_param/` |
| **Combined Dashboard Maps** | Side-by-side comparison of all parameters | `maps/output/combined/` |

---

### Key Folium/Leaflet Features Used

1. **Base Maps**: OpenStreetMap, CartoDB Positron tiles
2. **GeoJSON Rendering**: District boundaries with custom styling
3. **Interactive Layers**: Tooltips, popups, hover highlights
4. **Markers**: Circle markers for points, DivIcons for labels
5. **Choropleth**: Color-coded districts based on data values
6. **Custom HTML**: Titles, legends, multi-parameter panels