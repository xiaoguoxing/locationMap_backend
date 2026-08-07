#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Choropleth Mapper - Generate district-level choropleth maps

Uses the official HK government 18-district boundary GeoJSON
and folium.GeoJson for proper district boundary visualization.
"""

import os
import json
import folium
import pandas as pd
from typing import Optional, Dict, List, Tuple

from district_aggregator import get_color_for_district
from reference_layer import add_tpu_reference

# District name mapping: English -> Traditional Chinese
DISTRICT_NAMES_TC = {
    'Central & Western': '\u4e2d\u897f\u5340',
    'Eastern': '\u6771\u5340',
    'Islands': '\u96e2\u5cf6\u5340',
    'Kowloon City': '\u4e5d\u9f8d\u57ce\u5340',
    'Kwai Tsing': '\u8475\u9752\u5340',
    'Kwun Tong': '\u89c0\u5858\u5340',
    'North': '\u5317\u5340',
    'Sai Kung': '\u897f\u8ca2\u5340',
    'Sha Tin': '\u6c99\u7530\u5340',
    'Sham Shui Po': '\u6df1\u6c34\u57d7\u5340',
    'Southern': '\u5357\u5340',
    'Tai Po': '\u5927\u57d4\u5340',
    'Tsuen Wan': '\u8343\u7063\u5340',
    'Tuen Mun': '\u5c6f\u9580\u5340',
    'Wan Chai': '\u7063\u4ed4\u5340',
    'Wong Tai Sin': '\u9ec3\u5927\u4ed9\u5340',
    'Yau Tsim Mong': '\u6cb9\u5c16\u65fa\u5340',
    'Yuen Long': '\u5143\u6717\u5340'
}

# Parameter display order and formatting info for multi-param maps
MULTI_PARAM_DISPLAY = {
    'cl2_free_1': {
        'display_name': 'Free Chlorine',
        'unit': 'mg/L',
        'short_name': 'Cl2',
        'icon': '&#x1F7E6;',
    },
    'ecoli': {
        'display_name': 'E. coli',
        'unit': 'cfu/100mL',
        'short_name': 'E.coli',
        'icon': '&#x1F7E9;',
    },
    'turby': {
        'display_name': 'Turbidity',
        'unit': 'NTU',
        'short_name': 'Turbidity',
        'icon': '&#x1F7E8;',
    }
}

PARAMETER_PRIORITY = ['cl2_free_1', 'ecoli', 'turby']

# ==========================================
# Configurable Display Settings
# ==========================================

# Font size (px) for district value labels rendered on the map.
# Increase if labels are too small or overlapping district boundaries.
# - Single-param maps: each label is one line, e.g. "0.45"
# - Multi-param maps: each label is multi-line, e.g. "Cl: 0.10<br>E.coli: 5.0"
DISTRICT_LABEL_FONT_SIZE = 10

# ==========================================
# Manual Centroid Adjustments for Problematic Districts
# ==========================================
#
# Some Hong Kong districts have complex multi-polygon geometries (islands, exclaves)
# that cause the calculated centroid to fall outside the visible landmass or
# be positioned poorly. This dictionary allows manual fine-tuning of label positions.
#
# Format: 'District Name': (delta_lat, delta_lon)
#   - Positive delta_lat shifts the label NORTH
#   - Positive delta_lon shifts the label EAST
#   - Negative delta_lat shifts the label SOUTH
#   - Negative delta_lon shifts the label WEST
#
# At Hong Kong's latitude (~22.3°N):
#   0.001° lat ≈ 111m  (use this for very fine adjustments)
#   0.005° lat ≈ 555m  (use this for small visible shifts)
#   0.010° lat ≈ 1.1km (use this for moderate shifts)
#   0.020° lat ≈ 2.2km (use this for larger shifts)
#
# To tune these values:
#   1. Generate a map and inspect label placement
#   2. Increase/decrease the delta value iteratively
#   3. Regenerate the map to verify
DISTRICT_CENTROID_ADJUSTMENTS = {
    # Tsuen Wan: shift north substantially (~total height of legend, 3 lines of text)
    'Tsuen Wan': (0.018, 0.0),
    # Kwun Tong: shift west by ~4 character widths
    'Kwun Tong': (0.0, -0.008),
    # North District: shift north (centroid pulled south by the long shape)
    'North': (0.005, 0.0),
    # Wong Tai Sin: shift slightly north
    'Wong Tai Sin': (0.003, 0.0),
    # Wan Chai: shift west by ~4 character widths
    'Wan Chai': (0.0, -0.008),
    # Add more districts here as needed. Example:
    # 'Sha Tin': (0.0, 0.0),
    # 'Yuen Long': (0.0, 0.0),
}


def calculate_polygon_centroid(coords: List[List[float]]) -> Tuple[float, float]:
    """
    Calculate the geometric centroid (area-weighted center) of a polygon using the shoelace formula.
    
    This is more accurate than simply averaging vertices, especially for irregular shapes
    like Hong Kong's districts which may have complex boundaries and islands.
    
    Args:
        coords: List of [lon, lat] coordinates forming the polygon ring (first = last)
        
    Returns:
        Tuple of (centroid_lon, centroid_lat)
    """
    if len(coords) < 3:
        # Not a valid polygon, fall back to simple average
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        return sum(lons) / len(lons), sum(lats) / len(lats)
    
    # Remove duplicate last point if present
    if coords[0][0] == coords[-1][0] and coords[0][1] == coords[-1][1]:
        coords = coords[:-1]
    
    n = len(coords)
    area = 0.0
    cx = 0.0
    cy = 0.0
    
    for i in range(n):
        j = (i + 1) % n
        xi, yi = coords[i][0], coords[i][1]
        xj, yj = coords[j][0], coords[j][1]
        
        # Shoelace formula for signed area
        cross = xi * yj - xj * yi
        area += cross
        
        # Centroid calculation weighted by area contribution
        cx += (xi + xj) * cross
        cy += (yi + yj) * cross
    
    if abs(area) < 1e-10:
        # Degenerate polygon, fall back to simple average
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        return sum(lons) / len(lons), sum(lats) / len(lats)
    
    area = 0.5 * area
    cx = cx / (6.0 * area)
    cy = cy / (6.0 * area)
    
    return cx, cy


def get_geojson_centroid(geometry: Dict) -> Optional[Tuple[float, float]]:
    """
    Calculate centroid for a GeoJSON geometry (Polygon or MultiPolygon).
    
    For MultiPolygon:
    - Finds the polygon with the largest area and returns its centroid
    - Alternatively can do area-weighted average of all polygon centroids
    
    Args:
        geometry: GeoJSON geometry dict with 'type' and 'coordinates'
        
    Returns:
        Tuple of (centroid_lon, centroid_lat) or None if invalid
    """
    if geometry['type'] == 'Polygon':
        # Each Polygon has: [outer_ring, hole1, hole2, ...]
        # We use only the outer ring for centroid calculation
        outer_ring = geometry['coordinates'][0]
        return calculate_polygon_centroid(outer_ring)
        
    elif geometry['type'] == 'MultiPolygon':
        # MultiPolygon: [[[outer1, hole1...], [outer2, hole2...]], ...]
        # For Hong Kong districts like Islands, we want the "visual center"
        # Strategy: calculate centroid of each polygon, pick the largest one
        
        largest_area = -1
        best_centroid = None
        all_centroids = []
        all_areas = []
        
        for polygon in geometry['coordinates']:
            outer_ring = polygon[0]
            centroid = calculate_polygon_centroid(outer_ring)
            
            # Calculate approximate area for weighting
            n = len(outer_ring)
            area = 0.0
            for i in range(n):
                j = (i + 1) % n
                area += abs(outer_ring[i][0] * outer_ring[j][1] - outer_ring[j][0] * outer_ring[i][1])
            area = 0.5 * area
            
            all_centroids.append(centroid)
            all_areas.append(area)
            
            if area > largest_area:
                largest_area = area
                best_centroid = centroid
        
        # Option 1: Just use the largest polygon's centroid (good for islands with one major landmass)
        # return best_centroid
        
        # Option 2: Area-weighted average of all polygon centroids (more representative overall)
        total_area = sum(all_areas)
        if total_area > 0:
            weighted_lon = sum(c[0] * a for c, a in zip(all_centroids, all_areas)) / total_area
            weighted_lat = sum(c[1] * a for c, a in zip(all_centroids, all_areas)) / total_area
            return (weighted_lon, weighted_lat)
        
        return best_centroid
        
    return None


def get_adjusted_centroid(district: str, geometry: Dict) -> Optional[Tuple[float, float]]:
    """
    Calculate centroid and apply any manual adjustments for the district.
    
    First computes the geometric centroid using get_geojson_centroid(),
    then applies any manual offsets defined in DISTRICT_CENTROID_ADJUSTMENTS.
    This is a safe approach because:
    - The geometric centroid is always calculated as fallback
    - Manual offsets are small deltas (not hard-coded positions)
    - Unadjusted districts are unaffected
    - Offsets can be independently tuned per district
    
    Args:
        district: District name (e.g., "Tsuen Wan")
        geometry: GeoJSON geometry dict
        
    Returns:
        Tuple of (adjusted_lon, adjusted_lat) or None if invalid
    """
    centroid = get_geojson_centroid(geometry)
    if centroid is None:
        return None
    
    centroid_lon, centroid_lat = centroid
    
    # Apply manual adjustment if defined for this district
    if district in DISTRICT_CENTROID_ADJUSTMENTS:
        delta_lat, delta_lon = DISTRICT_CENTROID_ADJUSTMENTS[district]
        centroid_lat += delta_lat
        centroid_lon += delta_lon
        print(f"    [ADJUST] {district}: centroid shifted by (lat={delta_lat:.4f}, lon={delta_lon:.4f})")
    
    return (centroid_lon, centroid_lat)


def create_choropleth_map(
    district_stats: pd.DataFrame, 
    geojson_path: str, 
    parameter_name: str, 
    date_range: str, 
    output_path: str
) -> Optional[str]:
    """
    Create choropleth map for water quality parameter.
    
    Args:
        district_stats: Aggregated district statistics with 'normalized_district' column
        geojson_path: Path to official HK districts GeoJSON
        parameter_name: Parameter name (e.g., "cl2_free_1", "ecoli")
        date_range: Date range for the data
        output_path: Output HTML file path
    
    Returns:
        Path to generated HTML file or None if failed
    """
    with open(geojson_path, 'r', encoding='utf-8') as f:
        geojson_data = json.load(f)
    
    if 'cl2' in parameter_name.lower() or 'free' in parameter_name.lower():
        value_column = 'mean'
        unit = 'mg/L'
        param_display = 'Chlorine (Free)'
    elif 'eco' in parameter_name.lower() or 'coli' in parameter_name.lower():
        value_column = 'mean'
        unit = 'cfu/100mL'
        param_display = 'E. coli'
    elif 'turb' in parameter_name.lower():
        value_column = 'mean'
        unit = 'NTU'
        param_display = 'Turbidity'
    else:
        value_column = 'mean'
        unit = ''
        param_display = parameter_name
    
    district_values = {}
    for _, row in district_stats.iterrows():
        district_name = row['normalized_district']
        value = row.get(value_column, None)
        if value is not None and pd.notna(value):
            district_values[district_name] = float(value)
    
    print("  [CHORO] District values: {} districts with data".format(len(district_values)))
    
    m = folium.Map(location=[22.3193, 114.1694], zoom_start=10, tiles='CartoDB positron')
    
    def style_function(feature):
        district = feature['properties']['District']
        if district in district_values:
            value = district_values[district]
            color = get_color_for_district(value, parameter_name)
            return {'fillColor': color, 'color': 'white', 'weight': 1.5, 'fillOpacity': 0.7}
        else:
            return {'fillColor': '#cccccc', 'color': 'white', 'weight': 1.5, 'fillOpacity': 0.3}
    
    def highlight_function(feature):
        return {'fillColor': '#ffff00', 'color': 'red', 'weight': 2, 'fillOpacity': 0.9}
    
    geojson_layer = folium.GeoJson(
        geojson_data,
        style_function=style_function,
        highlight_function=highlight_function,
        name='District Choropleth'
    )
    
    folium.GeoJsonTooltip(
        fields=['District'],
        aliases=['District:'],
        style=("background-color: white; color: black; font-size: 12px; padding: 5px;")
    ).add_to(geojson_layer)
    
    def popup_content(feature):
        district = feature['properties']['District']
        district_tc = DISTRICT_NAMES_TC.get(district, district)
        if district in district_values:
            value = district_values[district]
            stats_row = district_stats[district_stats['normalized_district'] == district]
            if len(stats_row) > 0:
                stats = stats_row.iloc[0]
                count = int(stats.get('count', 0))
                max_val = stats.get('max', None)
                popup_text = "<b>{} ({})</b><br>".format(district_tc, district)
                popup_text += "Average: {:.3f} {}<br>".format(value, unit)
                if max_val is not None and pd.notna(max_val):
                    popup_text += "Max: {:.3f} {}<br>".format(max_val, unit)
                popup_text += "Samples: {}".format(count)
                return popup_text
        return "<b>{} ({})</b><br>No data available".format(district_tc, district)
    
    folium.GeoJsonPopup(
        fields=[], labels=False,
        style=("background-color: white; color: black; font-size: 13px; padding: 10px;")
    ).add_to(geojson_layer)
    
    geojson_layer.add_to(m)
    
    # 叠加 TPU 参考线框（纯装饰，压在分区色块之上）
    add_tpu_reference(m)
    
    for feature in geojson_data['features']:
        district = feature['properties']['District']
        if district in district_values:
            # Use area-weighted centroid calculation with manual adjustments
            centroid = get_adjusted_centroid(district, feature['geometry'])
            if centroid is None:
                continue
            centroid_lon, centroid_lat = centroid
            
            value = district_values[district]
            if 'eco' in parameter_name.lower() or 'coli' in parameter_name.lower():
                label = "{:.1f}".format(value)
            else:
                label = "{:.2f}".format(value)
            folium.Marker(
                location=[centroid_lat, centroid_lon],
                icon=folium.DivIcon(
                    html='<div style="font-size:{}px;font-weight:bold;color:#333;text-align:center;white-space:nowrap;text-shadow:-1px -1px 0 #fff,1px -1px 0 #fff,-1px 1px 0 #fff,1px 1px 0 #fff;background:rgba(255,255,255,0.75);border-radius:3px;padding:1px 3px;">{}</div>'.format(DISTRICT_LABEL_FONT_SIZE, label),
                    class_name='district-label'
                )
            ).add_to(m)
    
    # Build parameter-specific legend in the compact bottom-left style
    # (consistent with multi-param maps)
    panel_parts = []
    panel_parts.append(
        '<div style="position:fixed;bottom:10px;left:10px;'
        'background-color:rgba(255,255,255,0.95);border:1px solid #999;border-radius:4px;'
        'padding:6px 8px;z-index:9999;font-size:11px;max-width:380px;'
        'box-shadow:0 1px 4px rgba(0,0,0,0.15);line-height:1.4;">'
        '<b style="font-size:12px;">{} (Avg)</b> &nbsp;'
        '<span style="color:#555;">{}</span> &nbsp; '
        '<span style="color:#555;">{}/18 districts</span><br>'.format(
            param_display, date_range, len(district_values))
    )
    
    # Add color scale specific to this parameter
    if 'cl2' in parameter_name.lower() or 'free' in parameter_name.lower():
        # RED: <0.2 (insufficient) OR >3.0 (very high)
        # GREEN: 0.2-1.5 (ideal range)
        # ORANGE: 1.5-2.0 (slightly elevated)
        # DARKRED: 2.0-3.0 (high)
        panel_parts.append(
            '<div style="margin:2px 0;">'
            '<b>Cl₂ (Avg)</b>: '
            '<span style="display:inline-block;background:red;width:10px;height:10px;margin:0 2px;vertical-align:middle;opacity:0.7;"></span>'
            '<span><0.2</span> '
            '<span style="display:inline-block;background:green;width:10px;height:10px;margin:0 2px;vertical-align:middle;"></span>'
            '<span>0.2–1.5</span> '
            '<span style="display:inline-block;background:orange;width:10px;height:10px;margin:0 2px;vertical-align:middle;"></span>'
            '<span>1.6–2.0</span> '
            '<span style="display:inline-block;background:darkred;width:10px;height:10px;margin:0 2px;vertical-align:middle;opacity:0.7;"></span>'
            '<span>2.1–3.0</span> '
            '<span style="display:inline-block;background:red;width:10px;height:10px;margin:0 2px;vertical-align:middle;"></span>'
            '<span>>3.0 mg/L</span>'
            '</div>'
        )
    elif 'eco' in parameter_name.lower() or 'coli' in parameter_name.lower():
        panel_parts.append(
            '<div style="margin:2px 0;">'
            '<b>E.coli (Avg)</b>: '
            '<span style="display:inline-block;background:green;width:10px;height:10px;margin:0 2px;vertical-align:middle;"></span>'
            '<span>0</span> '
            '<span style="display:inline-block;background:red;width:10px;height:10px;margin:0 2px;vertical-align:middle;"></span>'
            '<span>Any value >0</span>'
            '</div>'
        )
    elif 'turb' in parameter_name.lower():
        panel_parts.append(
            '<div style="margin:2px 0;">'
            '<b>Turbidity (Avg)</b>: '
            '<span style="display:inline-block;background:green;width:10px;height:10px;margin:0 2px;vertical-align:middle;"></span>'
            '<span>≤1.5</span> '
            '<span style="display:inline-block;background:orange;width:10px;height:10px;margin:0 2px;vertical-align:middle;"></span>'
            '<span>1.6–3.0</span> '
            '<span style="display:inline-block;background:darkred;width:10px;height:10px;margin:0 2px;vertical-align:middle;opacity:0.7;"></span>'
            '<span>3.1–10.0</span> '
            '<span style="display:inline-block;background:red;width:10px;height:10px;margin:0 2px;vertical-align:middle;"></span>'
            '<span>>10.0 NTU</span>'
            '</div>'
        )
    else:
        # Generic legend
        panel_parts.append(
            '<div style="margin:2px 0;">'
            '<span style="display:inline-block;background:green;width:10px;height:10px;margin:0 2px;vertical-align:middle;"></span>'
            '<span>Normal/Good</span> '
            '<span style="display:inline-block;background:orange;width:10px;height:10px;margin:0 2px;vertical-align:middle;"></span>'
            '<span>Warning</span> '
            '<span style="display:inline-block;background:red;width:10px;height:10px;margin:0 2px;vertical-align:middle;"></span>'
            '<span>Critical</span>'
            '</div>'
        )
    
    panel_parts.append('</div>')
    
    m.get_root().html.add_child(folium.Element(''.join(panel_parts)))
    
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    m.save(output_path)
    print("  [SUCCESS] Choropleth map saved: {}".format(output_path))
    return output_path


# ==========================================
# Multi-Parameter Choropleth Map
# ==========================================


def create_multi_param_choropleth_map(
    merged_district_data: Dict[str, Dict],
    geojson_path: str,
    date_range: str,
    color_parameter: str,
    output_path: str
) -> Optional[str]:
    """
    Create a choropleth map showing all water quality parameters per district.
    
    Each district displays all available parameter average values in the 
    tooltip/popup. The choropleth fill color is determined by the primary
    (color_parameter) parameter's value.
    """
    with open(geojson_path, 'r', encoding='utf-8') as f:
        geojson_data = json.load(f)
    
    # Build district value lookup for the color parameter
    district_color_values = {}
    for district, params in merged_district_data.items():
        if color_parameter in params and params[color_parameter].get('avg') is not None:
            district_color_values[district] = params[color_parameter]['avg']
    
    color_param_info = MULTI_PARAM_DISPLAY.get(color_parameter, {
        'display_name': color_parameter, 'unit': '', 'short_name': color_parameter, 'icon': '&#x26AA;'
    })
    
    print("  [CHORO-MULTI] Districts with color data: {}".format(len(district_color_values)))
    print("  [CHORO-MULTI] Color parameter: {}".format(color_param_info['display_name']))
    
    m = folium.Map(location=[22.3193, 114.1694], zoom_start=10, tiles='CartoDB positron')
    
    def style_function(feature):
        district = feature['properties']['District']
        if district in district_color_values:
            value = district_color_values[district]
            color = get_color_for_district(value, color_parameter)
            return {'fillColor': color, 'color': 'white', 'weight': 1.5, 'fillOpacity': 0.7}
        else:
            return {'fillColor': '#cccccc', 'color': 'white', 'weight': 1.5, 'fillOpacity': 0.3}
    
    def highlight_function(feature):
        return {'fillColor': '#ffff00', 'color': 'red', 'weight': 2, 'fillOpacity': 0.9}
    
    # Inject popup HTML into each GeoJSON feature's properties
    # Folium's GeoJsonPopup reads from feature properties, not Python callbacks
    for feature in geojson_data['features']:
        district = feature['properties']['District']
        district_tc = DISTRICT_NAMES_TC.get(district, district)
        
        if district not in merged_district_data:
            feature['properties']['popup_html'] = "<b>{} ({})</b><br>No data available".format(district_tc, district)
            feature['properties']['tooltip_html'] = district_tc
            continue
        
        params = merged_district_data[district]
        
        # Build popup content with all 3 parameters
        parts = []
        parts.append('<div style="font-family:Arial,sans-serif;font-size:13px;min-width:240px;">')
        parts.append('<b style="font-size:15px;">{} ({})</b><br>'.format(district_tc, district))
        parts.append('<hr style="margin:4px 0;border:none;border-top:1px solid #ccc;">')
        
        for param_key in PARAMETER_PRIORITY:
            pdi = MULTI_PARAM_DISPLAY.get(param_key, {
                'display_name': param_key, 'unit': '', 'short_name': param_key, 'icon': '&#x26AA;'
            })
            
            if param_key in params and params[param_key].get('avg') is not None:
                avg_val = params[param_key]['avg']
                max_val = params[param_key].get('max')
                count = params[param_key].get('count', 0)
                unit = params[param_key].get('unit', pdi['unit'])
                
                if 'eco' in param_key.lower() or 'coli' in param_key.lower():
                    avg_str = "{:.1f}".format(avg_val)
                    max_str = "{:.0f}".format(max_val) if max_val is not None else None
                else:
                    avg_str = "{:.3f}".format(avg_val)
                    max_str = "{:.3f}".format(max_val) if max_val is not None else None
                
                parts.append('<div style="margin:4px 0;padding:2px 4px;background:#f8f9fa;border-radius:3px;">')
                parts.append('<b>{} {} (Avg):</b> {} {}'.format(
                    pdi['icon'], pdi['display_name'], avg_str, unit))
                if max_str is not None:
                    parts.append('<br><small>&nbsp;&nbsp;Max: {} {}</small>'.format(max_str, unit))
                parts.append('<br><small>&nbsp;&nbsp;Samples: {}</small>'.format(count))
                parts.append('</div>')
            else:
                parts.append('<div style="margin:4px 0;padding:2px 4px;color:#999;">')
                parts.append('<b>{} {} (Avg):</b> No data'.format(pdi['icon'], pdi['display_name']))
                parts.append('</div>')
        
        parts.append('<hr style="margin:4px 0;border:none;border-top:1px solid #ccc;">')
        parts.append('<small style="color:#666;">All values are district averages</small>')
        parts.append('</div>')
        
        feature['properties']['popup_html'] = ''.join(parts)
        
        # Build short tooltip showing all param values on one line
        tooltip_parts = []
        for param_key in PARAMETER_PRIORITY:
            if param_key in params and params[param_key].get('avg') is not None:
                pdi = MULTI_PARAM_DISPLAY.get(param_key, {'short_name': param_key, 'unit': ''})
                avg_val = params[param_key]['avg']
                unit = params[param_key].get('unit', pdi.get('unit', ''))
                if 'eco' in param_key.lower() or 'coli' in param_key.lower():
                    tooltip_parts.append("{}: {:.1f}".format(pdi['short_name'], avg_val))
                else:
                    tooltip_parts.append("{}: {:.2f}".format(pdi['short_name'], avg_val))
        
        feature['properties']['tooltip_html'] = district_tc + '<br>' + ' | '.join(tooltip_parts)
    
    geojson_layer = folium.GeoJson(
        geojson_data,
        style_function=style_function,
        highlight_function=highlight_function,
        name='District Choropleth (All Parameters)'
    )
    
    folium.GeoJsonTooltip(
        fields=['tooltip_html'],
        labels=False,
        style=("background-color: white; color: black; font-size: 12px; padding: 8px; min-width: 200px;")
    ).add_to(geojson_layer)
    
    folium.GeoJsonPopup(
        fields=['popup_html'],
        labels=False,
        style=("background-color:white;color:black;font-size:13px;padding:10px;min-width:280px;")
    ).add_to(geojson_layer)
    
    geojson_layer.add_to(m)
    
    # 叠加 TPU 参考线框（纯装饰，压在分区色块之上）
    add_tpu_reference(m)
    
    # Add value labels on each district - show all 3 parameter values
    for feature in geojson_data['features']:
        district = feature['properties']['District']
        if district in merged_district_data:
            # Use area-weighted centroid calculation with manual adjustments
            centroid = get_adjusted_centroid(district, feature['geometry'])
            if centroid is None:
                continue
            centroid_lon, centroid_lat = centroid
            
            # Build multi-param label: "Cl: 0.10 | E.coli: 5.0 | Turb: 0.50"
            params = merged_district_data[district]
            label_parts = []
            for param_key in PARAMETER_PRIORITY:
                if param_key in params and params[param_key].get('avg') is not None:
                    pdi = MULTI_PARAM_DISPLAY.get(param_key, {'short_name': param_key, 'unit': ''})
                    avg_val = params[param_key]['avg']
                    unit = params[param_key].get('unit', pdi.get('unit', ''))
                    if 'eco' in param_key.lower() or 'coli' in param_key.lower():
                        label_parts.append("{}: {:.1f}".format(pdi['short_name'], avg_val))
                    else:
                        label_parts.append("{}: {:.2f}".format(pdi['short_name'], avg_val))
            
            if label_parts:
                label = '<br>'.join(label_parts)
            else:
                label = district
            
            folium.Marker(
                location=[centroid_lat, centroid_lon],
                icon=folium.DivIcon(
                    html='<div style="font-size:{}px;font-weight:bold;color:#333;text-align:center;white-space:nowrap;line-height:1.3;text-shadow:-1px -1px 0 #fff,1px -1px 0 #fff,-1px 1px 0 #fff,1px 1px 0 #fff;background:rgba(255,255,255,0.75);border-radius:3px;padding:1px 3px;">{}</div>'.format(DISTRICT_LABEL_FONT_SIZE, label),
                    class_name='district-label'
                )
            ).add_to(m)
    
    # Build list of available parameters for title/legend
    available_params = set()
    for district, params in merged_district_data.items():
        for p in params:
            if params[p].get('avg') is not None:
                available_params.add(p)
    
    available_param_names = []
    for p in PARAMETER_PRIORITY:
        if p in available_params:
            info = MULTI_PARAM_DISPLAY.get(p, {})
            available_param_names.append(info.get('display_name', p))
    
    params_str = ', '.join(available_param_names)
    
    # Ultra-compact combined panel at bottom-left (title + legend merged)
    panel_parts = []
    panel_parts.append(
        '<div style="position:fixed;bottom:10px;left:10px;'
        'background-color:rgba(255,255,255,0.95);border:1px solid #999;border-radius:4px;'
        'padding:6px 8px;z-index:9999;font-size:11px;max-width:420px;'
        'box-shadow:0 1px 4px rgba(0,0,0,0.15);line-height:1.4;">'
        '<b style="font-size:12px;">All Parameters (Avg)</b> &nbsp;'
        '<span style="color:#555;">{}</span> &nbsp; '
        '<span style="color:#555;">{}/18 districts</span> &nbsp; '
        '<small style="color:#888;">Color: {}</small><br>'.format(
            date_range, len(district_color_values), color_param_info['display_name'])
    )
    
    # Inline color scale per parameter (one line each)
    for param_key in PARAMETER_PRIORITY:
        pdi = MULTI_PARAM_DISPLAY.get(param_key, {
            'display_name': param_key, 'unit': '', 'short_name': param_key, 'icon': '&#x26AA;'
        })
        
        if param_key in available_params:
            if 'cl2' in param_key.lower() or 'free' in param_key.lower():
                # RED: <0.2 (insufficient) OR >3.0 (very high)
                # GREEN: 0.2-1.5 (ideal range)
                # ORANGE: 1.5-2.0 (slightly elevated)
                # DARKRED: 2.0-3.0 (high)
                panel_parts.append(
                    '<div style="margin:2px 0;">'
                    '<b>Cl\u2082 (Avg)</b>: '
                    '<span style="display:inline-block;background:red;width:10px;height:10px;margin:0 2px;vertical-align:middle;opacity:0.7;"></span>'
                    '<span><0.2</span> '
                    '<span style="display:inline-block;background:green;width:10px;height:10px;margin:0 2px;vertical-align:middle;"></span>'
                    '<span>0.2\u20131.5</span> '
                    '<span style="display:inline-block;background:orange;width:10px;height:10px;margin:0 2px;vertical-align:middle;"></span>'
                    '<span>1.6\u20132.0</span> '
                    '<span style="display:inline-block;background:darkred;width:10px;height:10px;margin:0 2px;vertical-align:middle;opacity:0.7;"></span>'
                    '<span>2.1\u20133.0</span> '
                    '<span style="display:inline-block;background:red;width:10px;height:10px;margin:0 2px;vertical-align:middle;"></span>'
                    '<span>>3.0 mg/L</span>'
                    '</div>'
                )
            elif 'eco' in param_key.lower() or 'coli' in param_key.lower():
                panel_parts.append(
                    '<div style="margin:2px 0;">'
                    '<b>E.coli (Avg)</b>: '
                    '<span style="display:inline-block;background:green;width:10px;height:10px;margin:0 2px;vertical-align:middle;"></span>'
                    '<span>0</span> '
                    '<span style="display:inline-block;background:red;width:10px;height:10px;margin:0 2px;vertical-align:middle;"></span>'
                    '<span>Any value >0</span>'
                    '</div>'
                )
            elif 'turb' in param_key.lower():
                panel_parts.append(
                    '<div style="margin:2px 0;">'
                    '<b>Turb (Avg)</b>: '
                    '<span style="display:inline-block;background:green;width:10px;height:10px;margin:0 2px;vertical-align:middle;"></span>'
                    '<span>\u22641.5</span> '
                    '<span style="display:inline-block;background:orange;width:10px;height:10px;margin:0 2px;vertical-align:middle;"></span>'
                    '<span>1.6\u20133.0</span> '
                    '<span style="display:inline-block;background:darkred;width:10px;height:10px;margin:0 2px;vertical-align:middle;opacity:0.7;"></span>'
                    '<span>3.1\u201310.0</span> '
                    '<span style="display:inline-block;background:red;width:10px;height:10px;margin:0 2px;vertical-align:middle;"></span>'
                    '<span>>10.0 NTU</span>'
                    '</div>'
                )
        else:
            panel_parts.append(
                '<div style="margin:2px 0;color:#999;">'
                '<b>{} (Avg):</b> No data</div>'
                .format(pdi['display_name'])
            )
    
    panel_parts.append('</div>')
    
    m.get_root().html.add_child(folium.Element(''.join(panel_parts)))
    
    # Save map
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    m.save(output_path)
    print("  [SUCCESS] Multi-param choropleth map saved: {}".format(output_path))
    return output_path
