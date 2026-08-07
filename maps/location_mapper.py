#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
"""
Location Mapper - Generate interactive maps from CSV water quality data
Processes cl2_free_1, ecoli, and turby parameters with both point and district-level views
"""

import os
import sys
import argparse
import pandas as pd
import folium
from folium import CircleMarker
import re
import csv
import io
from pathlib import Path
from typing import Optional, Tuple, List, Union

# Import new modules
from district_aggregator import aggregate_water_quality
from choropleth_mapper import create_choropleth_map
from reference_layer import add_tpu_reference

# Force UTF-8 encoding for stdout/stderr on Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)

def read_and_filter_csv(csv_path: str) -> pd.DataFrame:
    """
    Read CSV file and filter out entries with missing GPS coordinates
    
    Args:
        csv_path: Path to CSV file
        
    Returns:
        Filtered DataFrame with valid GPS coordinates
    """
    print(f"  [READ] Reading CSV: {os.path.basename(csv_path)}")
    
    try:
        # Read the entire file to check for potential issues
        with open(csv_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            print(f"  [DEBUG] Total lines: {len(lines)}")
            
            # Check the problematic line
            if len(lines) > 230:
                print(f"  [DEBUG] Line 231: {repr(lines[230])}")
        
        # Read CSV with more robust parsing
        df = pd.read_csv(csv_path,
                          encoding='utf-8',
                          on_bad_lines='skip',  # Skip bad lines instead of raising an error
                          dtype=str,            # Read all columns as strings to prevent parsing errors
                          skipinitialspace=True,  # Skip initial whitespace
                          quoting=csv.QUOTE_MINIMAL,  # Minimal quoting
                          lineterminator='\n')  # Explicitly set line terminator
        
        total_rows = len(df)
        print(f"  [INFO] Total rows read: {total_rows}")
        print(f"  [INFO] Available columns: {list(df.columns)}")
        
        # Normalize column names (lowercase, remove whitespace)
        df.columns = [str(col).lower().strip() for col in df.columns]
        
        # Check required columns exist
        required_cols = ['result', 'district']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            print(f"  [WARN] Missing columns: {missing_cols}")
        
        # Load district GPS coordinates
        district_gps = pd.read_csv('gencsv/missing_gps/district_gps.csv')
        district_gps['district'] = district_gps['District'].str.lower()
        
        # Normalize district names
        df['district'] = df['district'].astype(str).str.lower()
        
        # Identify GPS coordinate columns with multiple possible names
        gps_lat_cols = [
            'loc_gps_latitude', 
            'loc_gps_latitude_value', 
            'latitude', 
            'lat'
        ]
        gps_lon_cols = [
            'loc_gps_longitude', 
            'loc_gps_longitude_value', 
            'longitude', 
            'lon'
        ]
        
        # Find the first available GPS column
        def find_first_valid_column(df: pd.DataFrame, column_list: List[str]) -> Optional[str]:
            for col in column_list:
                if col in df.columns and df[col].notna().any():
                    return col
            return None
        
        lat_col = find_first_valid_column(df, gps_lat_cols)
        lon_col = find_first_valid_column(df, gps_lon_cols)
        
        # If no GPS columns found, use district GPS
        if not lat_col or not lon_col:
            print("  [WARN] No GPS coordinates column found. Using district coordinates.")
            df = df.merge(district_gps[['district', 'Latitude', 'Longitude']], 
                          on='district', 
                          how='left')
            lat_col = 'Latitude'
            lon_col = 'Longitude'
        
        # Rename columns for consistency
        df.rename(columns={
            lat_col: 'loc_gps_latitude', 
            lon_col: 'loc_gps_longitude'
        }, inplace=True)
        
        # Filter out rows with missing GPS coordinates
        valid_gps = (
            df['loc_gps_latitude'].notna() & 
            df['loc_gps_longitude'].notna() &
            (df['loc_gps_latitude'].astype(str).str.strip() != '') &
            (df['loc_gps_longitude'].astype(str).str.strip() != '')
        )
        
        df_filtered = df[valid_gps].copy()
        filtered_rows = total_rows - len(df_filtered)
        
        print(f"  [FILTER] Rows filtered out (missing GPS): {filtered_rows}")
        print(f"  [KEEP] Rows kept for mapping: {len(df_filtered)}")
        
        # Convert GPS coordinates to float
        df_filtered['loc_gps_latitude'] = pd.to_numeric(df_filtered['loc_gps_latitude'], errors='coerce')
        df_filtered['loc_gps_longitude'] = pd.to_numeric(df_filtered['loc_gps_longitude'], errors='coerce')
        
        # Convert result to numeric
        df_filtered['result'] = pd.to_numeric(df_filtered['result'], errors='coerce')
        
        return df_filtered
        
    except FileNotFoundError:
        print(f"  [ERROR] File not found: {csv_path}")
        raise
    except pd.errors.EmptyDataError:
        print(f"  [ERROR] CSV file is empty: {csv_path}")
        raise
    except Exception as e:
        print(f"  [ERROR] Error reading CSV: {str(e)}")
        raise

def parse_filename(filename: str) -> Tuple[str, str]:
    """
    Parse filename to extract parameter name and date range
    
    Args:
        filename: CSV filename
        
    Returns:
        Tuple of (parameter_name, date_range)
    """
    # Remove .csv extension
    name = filename.replace('.csv', '')
    
    # Split by underscores
    parts = name.split('_')
    
    # Extract parameter (first parts until date)
    # Look for date pattern (YYYY-MM-DD)
    date_idx = None
    for i, part in enumerate(parts):
        if re.match(r'\d{4}-\d{2}-\d{2}', part):
            date_idx = i
            break
    
    if date_idx:
        parameter = '_'.join(parts[:date_idx])
        # Date range is the next two parts (start and end dates)
        if date_idx + 1 < len(parts):
            date_range = f"{parts[date_idx]}_{parts[date_idx+1]}"
        else:
            date_range = parts[date_idx]
    else:
        # Fallback: use first part as parameter, rest as date range
        parameter = parts[0]
        date_range = '_'.join(parts[1:])
    
    return parameter, date_range

def process_csv_file(csv_path: str, detailed_output_dir: Path, district_output_dir: Path) -> Optional[Tuple[str, str]]:
    """
    Process a single CSV file and generate point and district maps
    
    Args:
        csv_path: Path to CSV file
        detailed_output_dir: Output directory for detailed point maps
        district_output_dir: Output directory for district choropleth maps
        
    Returns:
        Tuple of paths to generated HTML files or None if failed
    """
    try:
        # Parse filename
        filename = os.path.basename(csv_path)
        parameter, date_range = parse_filename(filename)
        
        print(f"  [INFO] Parameter: {parameter}, Date range: {date_range}")
        
        # Read and filter CSV
        df = read_and_filter_csv(csv_path)
        
        if len(df) == 0:
            print(f"  [WARN] No valid data points to plot")
            return None
        
        # Aggregate district-level statistics
        district_stats = aggregate_water_quality(
            df=df, 
            geojson_path='maps/data/hk_districts.geojson', 
            parameter_name=parameter
        )
        
        # Generate output filenames
        detailed_output_filename = filename.replace('.csv', '_detailed_map.html')
        district_output_filename = filename.replace('.csv', '_district_map.html')
        
        detailed_output_path = detailed_output_dir / detailed_output_filename
        district_output_path = district_output_dir / district_output_filename
        
        # Create detailed point map
        detailed_map = plot_map(
            df=df,
            parameter_name=parameter,
            date_range=date_range,
            output_path=str(detailed_output_path)
        )
        
        # Create district choropleth map
        district_map = create_choropleth_map(
            district_stats=district_stats,
            geojson_path='maps/data/hk_districts.geojson',
            parameter_name=parameter,
            date_range=date_range,
            output_path=str(district_output_path)
        )
        
        return detailed_map, district_map
        
    except Exception as e:
        print(f"  [ERROR] Failed to process {csv_path}: {str(e)}")
        return None

def plot_map(df: pd.DataFrame, parameter_name: str, date_range: str, output_path: str) -> Optional[str]:
    """
    Create interactive point map for water quality parameter
    
    Args:
        df: Filtered DataFrame with GPS data
        parameter_name: Parameter name (e.g., "cl2_free_1", "ecoli", "turby")
        date_range: Date range string
        output_path: Output HTML file path
        
    Returns:
        Path to generated HTML file or None if failed
    """
    print(f"  [MAP] Creating detailed point map for {parameter_name} ({date_range})")
    
    if len(df) == 0:
        print(f"  [WARN] No valid data points to plot")
        return None
    
    # Determine parameter type and settings
    param_type = parameter_name.lower().split('_')[0]
    
    if param_type == 'cl2' or 'free' in parameter_name.lower():
        # Chlorine
        get_color_func = get_chlorine_color
        unit = 'mg/L'
        param_display = 'Chlorine'
    elif 'eco' in parameter_name.lower() or 'coli' in parameter_name.lower():
        # E. coli
        get_color_func = get_ecoli_color
        unit = 'CFU/100mL'
        param_display = 'E. coli'
    elif 'turb' in parameter_name.lower():
        # Turbidity
        get_color_func = get_turby_color
        unit = 'NTU'
        param_display = 'Turbidity'
    else:
        # Default to chlorine
        get_color_func = get_chlorine_color
        unit = 'mg/L'
        param_display = parameter_name
    
    # Calculate map center
    center_lat = df['loc_gps_latitude'].mean()
    center_lon = df['loc_gps_longitude'].mean()
    
    # Create map
    m = folium.Map(location=[center_lat, center_lon], zoom_start=12)
    
    # Add title
    title_html = f'''
        <div style="position: fixed; 
                    top: 10px; left: 50px; width: 300px;
                    background-color: white; 
                    border: 2px solid grey;
                    border-radius: 5px;
                    padding: 10px;
                    z-index: 9999;
                    font-size: 14px;">
            <b>{param_display} Detailed Point Map</b><br>
            Parameter: {parameter_name}<br>
            Date Range: {date_range}<br>
            Data Points: {len(df)}
        </div>
    '''
    m.get_root().html.add_child(folium.Element(title_html))
    
    # 叠加 TPU 参考线框（先加线框，后加打点，保证采样点不被线框遮挡）
    add_tpu_reference(m)
    
    # Add markers
    for idx, row in df.iterrows():
        lat = row['loc_gps_latitude']
        lon = row['loc_gps_longitude']
        result = row['result']
        color = get_color_func(result)
        
        # Prepare popup content
        popup_content = f"""
        <b>Sample #:</b> {row.get('sampno', 'N/A')}<br>
        <b>Location Code:</b> {row.get('loccode', 'N/A')}<br>
        <b>Description:</b> {row.get('locdescr', 'N/A')}<br>
        <b>District:</b> {row.get('district', 'N/A')}<br>
        <b>Collection Date:</b> {row.get('coldate', 'N/A')}<br>
        <b>Result:</b> {result} {unit}<br>
        """
        
        # Add owner if present
        if 'owner' in row and pd.notna(row['owner']):
            popup_content += f"<b>Owner:</b> {row['owner']}<br>"
        
        # Create marker
        CircleMarker(
            location=[lat, lon],
            radius=7,
            color='black',
            weight=1,
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            popup=folium.Popup(popup_content, max_width=300),
            tooltip=f"{row.get('locdescr', 'Location')}: {result} {unit}"
        ).add_to(m)
    
    # Save map
    m.save(output_path)
    print(f"  [SUCCESS] Detailed point map saved: {output_path}")
    
    return output_path

def get_chlorine_color(value: float) -> str:
    """
    Get color for chlorine level
    
    Args:
        value: Chlorine level in mg/L
        
    Returns:
        Color name for map marker
    """
    if pd.isna(value):
        return 'gray'
    elif 0.2 <= value <= 1.5:
        return 'green'
    elif 1.6 <= value <= 2.0:
        return 'orange'
    elif 2.1 <= value <= 3.0:
        return 'orangered'
    else:
        return 'red'

def get_ecoli_color(value: float) -> str:
    """
    Get color for E. coli count
    
    Args:
        value: E. coli count in CFU/100mL
        
    Returns:
        Color name for map marker
    """
    if pd.isna(value):
        return 'gray'
    elif value == 0:
        return 'green'
    else:
        return 'red'

def get_turby_color(value: float) -> str:
    """
    Get color for turbidity level
    
    Args:
        value: Turbidity in NTU
        
    Returns:
        Color name for map marker
    """
    if pd.isna(value):
        return 'gray'
    elif value <= 1.5:
        return 'green'
    elif 1.6 <= value <= 3.0:
        return 'orange'
    elif 3.1 <= value <= 10.0:
        return 'orangered'
    else:
        return 'red'

def main():
    """
    Main entry point - process all CSV files
    """
    print("=" * 70)
    print("LOCATION MAPPER - Water Quality Map Generator")
    print("=" * 70)
    
    # Set paths - using maps/output for dashboard compatibility
    input_dir = Path('gencsv/output')
    detailed_output_dir = Path('maps/output/detailed')
    district_output_dir = Path('maps/output/district')
    
    print(f"\n[CONFIG] Input directory: {input_dir.absolute()}")
    print(f"[CONFIG] Detailed output directory: {detailed_output_dir.absolute()}")
    print(f"[CONFIG] District output directory: {district_output_dir.absolute()}")
    
    # Check if input directory exists
    if not input_dir.exists():
        print(f"\n[ERROR] Input directory does not exist: {input_dir.absolute()}")
        return
    
    # Create output directories
    detailed_output_dir.mkdir(parents=True, exist_ok=True)
    district_output_dir.mkdir(parents=True, exist_ok=True)
    
    # Find all CSV files
    csv_files = sorted(input_dir.glob('*.csv'))
    
    if not csv_files:
        print("\n[ERROR] No CSV files found!")
        print(f"        Looked in: {input_dir.absolute()}")
        return
    
    print(f"\n[INFO] Found {len(csv_files)} CSV file(s)")
    print("-" * 70)
    
    # Process all CSV files
    success_count = 0
    error_count = 0
    
    for i, csv_file in enumerate(csv_files, 1):
        progress_pct = (i / len(csv_files)) * 100
        print(f"\n[PROGRESS] Processing file {i}/{len(csv_files)} ({progress_pct:.1f}%)")
        print(f"[FILE] {csv_file.name}")
        
        result = process_csv_file(str(csv_file), detailed_output_dir, district_output_dir)
        
        if result:
            success_count += 1
            print(f"[SUCCESS] Maps generated: Detailed {result[0]}, District {result[1]}")
        else:
            error_count += 1
            print(f"[FAILED] Could not generate maps")
    
    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total files processed: {len(csv_files)}")
    print(f"Successful: {success_count}")
    print(f"Failed: {error_count}")
    print(f"\nDetailed output directory: {detailed_output_dir.absolute()}")
    print(f"District output directory: {district_output_dir.absolute()}")
    print("=" * 70)

if __name__ == '__main__':
    main()
