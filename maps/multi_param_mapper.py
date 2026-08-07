#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Multi-Parameter Mapper - Generate district maps combining all water quality parameters

Groups CSV files by date range and creates a single district map per date range
that displays all 3 parameters (Free Chlorine, E. coli, Turbidity) when hovering
over a district. Maps are generated even if some parameters are missing.

Output directory: maps/output/district_all_param/
Filename pattern: all_params_{date_from}_{date_to}_{timestamp}_district_map.html
"""

import os
import sys
import re
import csv
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, Tuple, Optional, List

# Import existing modules
from district_aggregator import aggregate_water_quality, load_district_mapping, normalize_district_name
from choropleth_mapper import create_multi_param_choropleth_map

# Force UTF-8 encoding for stdout/stderr on Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)


# Parameter metadata
PARAMETER_INFO = {
    'cl2_free_1': {
        'display_name': 'Free Chlorine',
        'unit': 'mg/L',
        'short_name': 'Cl₂'
    },
    'ecoli': {
        'display_name': 'E. coli',
        'unit': 'cfu/100mL',
        'short_name': 'E.coli'
    },
    'turby': {
        'display_name': 'Turbidity',
        'unit': 'NTU',
        'short_name': 'Turbidity'
    }
}

# Priority order for choropleth coloring when multiple parameters available
PARAMETER_PRIORITY = ['cl2_free_1', 'ecoli', 'turby']


def parse_csv_filename(filename: str) -> Tuple[str, str, str]:
    """
    Parse CSV filename to extract parameter name, date range key, and timestamp.
    
    Pattern: {parameter}_{date_from}_{date_to}_{timestamp}.csv
    Example: cl2_free_1_2025-10-26_2025-11-01_20260427_165324.csv
    
    Args:
        filename: CSV filename (with or without extension)
        
    Returns:
        Tuple of (parameter, date_range_key, timestamp)
        date_range_key format: "2025-10-26_2025-11-01"
    """
    name = filename.replace('.csv', '')
    parts = name.split('_')
    
    # Find the first date pattern (YYYY-MM-DD)
    date_idx = None
    for i, part in enumerate(parts):
        if re.match(r'\d{4}-\d{2}-\d{2}', part):
            date_idx = i
            break
    
    if date_idx:
        parameter = '_'.join(parts[:date_idx])
        date_from = parts[date_idx]
        date_to = parts[date_idx + 1] if (date_idx + 1) < len(parts) else None
        timestamp = '_'.join(parts[date_idx + 2:]) if (date_idx + 2) < len(parts) else None
        date_range_key = f"{date_from}_{date_to}" if date_to else date_from
    else:
        # Legacy format without date range
        parameter = parts[0]
        date_range_key = None
        timestamp = '_'.join(parts[1:]) if len(parts) > 1 else None
    
    return parameter, date_range_key, timestamp


def group_csvs_by_date_range(csv_dir: Path) -> Dict[str, Dict[str, Path]]:
    """
    Group CSV files by date range.
    
    Scans the directory, parses each filename, and groups files
    that share the same date range together.
    
    Args:
        csv_dir: Path to directory containing CSV files
        
    Returns:
        Dict mapping date_range_key to dict of {parameter: csv_path}
        Example: {'2025-10-26_2025-11-01': {'cl2_free_1': Path(...), 'ecoli': Path(...), 'turby': Path(...)}}
    """
    csv_files = sorted(csv_dir.glob('*.csv'))
    
    if not csv_files:
        print(f"  [WARN] No CSV files found in {csv_dir}")
        return {}
    
    date_groups = {}
    
    for csv_file in csv_files:
        parameter, date_range_key, timestamp = parse_csv_filename(csv_file.name)
        
        if not date_range_key:
            print(f"  [SKIP] No date range found in: {csv_file.name}")
            continue
        
        if date_range_key not in date_groups:
            date_groups[date_range_key] = {}
        
        date_groups[date_range_key][parameter] = csv_file
    
    return date_groups


def read_csv_safe(csv_path: Path, parameter: str) -> Optional[pd.DataFrame]:
    """
    Safely read a CSV file with error handling.
    
    Args:
        csv_path: Path to CSV file
        parameter: Parameter name for logging
        
    Returns:
        DataFrame or None if reading failed
    """
    try:
        df = pd.read_csv(
            csv_path,
            encoding='utf-8',
            on_bad_lines='skip',
            dtype=str,
            skipinitialspace=True,
            quoting=csv.QUOTE_MINIMAL,
            lineterminator='\n'
        )
        
        # Normalize column names
        df.columns = [str(col).lower().strip() for col in df.columns]
        
        # Convert result column to numeric
        if 'result' in df.columns:
            df['result'] = pd.to_numeric(df['result'], errors='coerce')
        
        # Check required columns
        required_cols = ['result', 'district']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            print(f"    [WARN] Missing columns in {csv_path.name}: {missing_cols}")
            return None
        
        if len(df) == 0:
            print(f"    [WARN] Empty CSV: {csv_path.name}")
            return None
        
        # Load district GPS coordinates for missing GPS data
        district_gps_path = Path('gencsv/missing_gps/district_gps.csv')
        if district_gps_path.exists():
            district_gps = pd.read_csv(district_gps_path)
            district_gps['district'] = district_gps['District'].str.lower()
            
            # Normalize district names
            df['district'] = df['district'].astype(str).str.lower()
            
            # Fill missing GPS from district GPS lookup
            if 'loc_gps_latitude' not in df.columns or 'loc_gps_longitude' not in df.columns:
                df = df.merge(
                    district_gps[['district', 'Latitude', 'Longitude']],
                    on='district', how='left'
                )
                if 'Latitude' in df.columns:
                    df['loc_gps_latitude'] = df['loc_gps_latitude'].fillna(df['Latitude'])
                    df['loc_gps_longitude'] = df['loc_gps_longitude'].fillna(df['Longitude'])
                    df = df.drop(columns=['Latitude', 'Longitude'], errors='ignore')
        
        valid_count = df['result'].notna().sum()
        print(f"    [OK] {parameter}: {len(df)} rows, {valid_count} valid results")
        
        return df
        
    except Exception as e:
        print(f"    [ERROR] Failed to read {csv_path.name}: {e}")
        return None


def aggregate_all_parameters(
    param_dataframes: Dict[str, pd.DataFrame],
    geojson_path: str
) -> Dict[str, Dict]:
    """
    Aggregate water quality data for all parameters and merge by district.
    
    For each available parameter, calls the existing aggregate_water_quality()
    function, then merges results into a unified district-level data structure.
    
    Args:
        param_dataframes: Dict mapping parameter name to its DataFrame
        geojson_path: Path to HK districts GeoJSON file
        
    Returns:
        Dict mapping district_name to dict of parameter info:
        {
            'Central & Western': {
                'cl2_free_1': {'avg': 0.45, 'max': 1.2, 'count': 15, 'unit': 'mg/L', 'display_name': 'Free Chlorine'},
                'ecoli': {'avg': 2.3, 'contamination_rate': 5.0, 'count': 12, 'unit': '%', 'display_name': 'E. coli'},
                'turby': {'avg': 0.28, 'max': 0.8, 'count': 18, 'unit': 'NTU', 'display_name': 'Turbidity'}
            },
            ...
        }
    """
    # Load district mapping for normalization
    district_mapping = load_district_mapping(geojson_path)
    
    # Aggregate each parameter
    param_stats = {}
    for param_name, df in param_dataframes.items():
        try:
            stats = aggregate_water_quality(df=df, geojson_path=geojson_path, parameter_name=param_name)
            param_stats[param_name] = stats
            print(f"    [AGG] {param_name}: {len(stats)} districts aggregated")
        except Exception as e:
            print(f"    [ERROR] Aggregation failed for {param_name}: {e}")
    
    # Merge results by district
    merged = {}
    
    # Get all district names from all parameter results
    all_districts = set()
    for param_name, stats in param_stats.items():
        if 'normalized_district' in stats.columns:
            all_districts.update(stats['normalized_district'].tolist())
    
    for district in all_districts:
        merged[district] = {}
        
        for param_name, stats in param_stats.items():
            param_info = PARAMETER_INFO.get(param_name, {
                'display_name': param_name,
                'unit': '',
                'short_name': param_name
            })
            
            # Find this district's row in the stats
            district_row = stats[stats['normalized_district'] == district]
            
            if len(district_row) > 0:
                row = district_row.iloc[0]
                
                # Determine the primary value based on parameter type
                if 'eco' in param_name.lower() or 'coli' in param_name.lower():
                    # E. coli: use mean as the primary value (cfu/100mL)
                    avg_value = row.get('mean', None)
                    if avg_value is not None and pd.notna(avg_value):
                        avg_value = float(avg_value)
                    max_value = row.get('max', None)
                    if max_value is not None and pd.notna(max_value):
                        max_value = float(max_value)
                else:
                    # Chlorine and Turbidity: use mean
                    avg_value = row.get('mean', None)
                    if avg_value is not None and pd.notna(avg_value):
                        avg_value = float(avg_value)
                    max_value = row.get('max', None)
                    if max_value is not None and pd.notna(max_value):
                        max_value = float(max_value)
                
                count = int(row.get('count', 0))
                
                merged[district][param_name] = {
                    'avg': avg_value,
                    'max': max_value,
                    'count': count,
                    'unit': param_info['unit'],
                    'display_name': param_info['display_name'],
                    'short_name': param_info['short_name']
                }
    
    return merged


def process_date_range_group(
    date_range_key: str,
    param_files: Dict[str, Path],
    geojson_path: str,
    output_dir: Path
) -> Optional[str]:
    """
    Process a single date range group and generate a combined district map.
    
    Loads available parameter CSVs, aggregates by district, and creates
    a multi-parameter choropleth map.
    
    Args:
        date_range_key: Date range string (e.g., "2025-10-26_2025-11-01")
        param_files: Dict mapping parameter name to its CSV file path
        geojson_path: Path to HK districts GeoJSON
        output_dir: Output directory for generated maps
        
    Returns:
        Path to generated HTML file or None if failed
    """
    parts = date_range_key.split('_')
    date_from = parts[0]
    date_to = parts[1] if len(parts) > 1 else parts[0]
    
    print(f"\n  [GROUP] Date range: {date_from} to {date_to}")
    print(f"  [GROUP] Available parameters: {list(param_files.keys())}")
    
    # Load available parameter CSVs
    param_dataframes = {}
    missing_params = []
    
    for param in PARAMETER_PRIORITY:
        if param in param_files:
            df = read_csv_safe(param_files[param], param)
            if df is not None and len(df) > 0:
                param_dataframes[param] = df
            else:
                missing_params.append(param)
        else:
            missing_params.append(param)
    
    if not param_dataframes:
        print(f"  [SKIP] No valid parameter data for date range {date_range_key}")
        return None
    
    if missing_params:
        print(f"  [INFO] Missing parameters: {missing_params}")
    
    # Aggregate all parameters by district
    merged_district_data = aggregate_all_parameters(param_dataframes, geojson_path)
    
    if not merged_district_data:
        print(f"  [SKIP] No district data generated for date range {date_range_key}")
        return None
    
    print(f"  [MERGE] {len(merged_district_data)} districts with data")
    
    # Generate timestamp for output filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_filename = f"all_params_{date_from}_{date_to}_{timestamp}_district_map.html"
    output_path = output_dir / output_filename
    
    # Determine which parameter drives the choropleth coloring
    color_param = None
    for param in PARAMETER_PRIORITY:
        if param in param_dataframes:
            color_param = param
            break
    
    # Create the multi-parameter choropleth map
    result = create_multi_param_choropleth_map(
        merged_district_data=merged_district_data,
        geojson_path=geojson_path,
        date_range=f"{date_from} to {date_to}",
        color_parameter=color_param,
        output_path=str(output_path)
    )
    
    if result:
        print(f"  [SUCCESS] Multi-param map saved: {output_filename}")
    
    return result


def main():
    """
    Main entry point - process all CSV files grouped by date range
    """
    print("=" * 70)
    print("MULTI-PARAMETER MAPPER - Combined Water Quality Map Generator")
    print("=" * 70)
    
    # Set paths - relative to this script's directory (maps/)
    script_dir = Path(__file__).parent
    input_dir = script_dir / '..' / 'gencsv' / 'output'
    output_dir = script_dir / 'output' / 'district_all_param'
    geojson_path = str(script_dir / 'data' / 'hk_districts.geojson')
    
    print(f"\n[CONFIG] Input directory: {input_dir.absolute()}")
    print(f"[CONFIG] Output directory: {output_dir.absolute()}")
    print(f"[CONFIG] GeoJSON path: {geojson_path}")
    
    # Check if input directory exists
    if not input_dir.exists():
        print(f"\n[ERROR] Input directory does not exist: {input_dir.absolute()}")
        return
    
    # Check if GeoJSON exists
    if not os.path.exists(geojson_path):
        print(f"\n[ERROR] GeoJSON file not found: {geojson_path}")
        return
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Group CSV files by date range
    print(f"\n[SCAN] Scanning CSV files in {input_dir}...")
    date_groups = group_csvs_by_date_range(input_dir)
    
    if not date_groups:
        print("\n[ERROR] No CSV files with date ranges found!")
        return
    
    print(f"\n[INFO] Found {len(date_groups)} unique date range(s)")
    print("-" * 70)
    
    # Process each date range group
    success_count = 0
    error_count = 0
    
    for i, (date_range_key, param_files) in enumerate(sorted(date_groups.items()), 1):
        progress_pct = (i / len(date_groups)) * 100
        print(f"\n[PROGRESS] Processing group {i}/{len(date_groups)} ({progress_pct:.1f}%)")
        
        result = process_date_range_group(
            date_range_key=date_range_key,
            param_files=param_files,
            geojson_path=geojson_path,
            output_dir=output_dir
        )
        
        if result:
            success_count += 1
        else:
            error_count += 1
    
    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total date range groups: {len(date_groups)}")
    print(f"Successful: {success_count}")
    print(f"Failed: {error_count}")
    print(f"\nOutput directory: {output_dir.absolute()}")
    print("=" * 70)


if __name__ == '__main__':
    main()
