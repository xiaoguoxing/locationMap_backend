#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
District Aggregator - Aggregate water quality data by district

Maps CSV neighborhood/area names to Hong Kong's 18 administrative districts
using the official HK government district boundaries.
"""

import pandas as pd
import json
import os
from typing import Dict, Optional

# Import neighborhood-to-district mapping
from data.district_mapping import NEIGHBORHOOD_TO_DISTRICT


def load_district_mapping(geojson_path: str) -> Dict[str, str]:
    """
    Load district names from GeoJSON and combine with neighborhood mapping.
    
    Creates a comprehensive mapping that handles:
    - Direct district name matches (case-insensitive)
    - Neighborhood/area name to district mapping
    - Common spelling variations
    
    Args:
        geojson_path: Path to districts GeoJSON file
    
    Returns:
        Dictionary mapping lowercase names → official district names
    """
    with open(geojson_path, 'r', encoding='utf-8') as f:
        districts_geojson = json.load(f)
    
    district_mapping = {}
    
    # Add neighborhood→district mappings from the explicit mapping table
    for neighborhood, district in NEIGHBORHOOD_TO_DISTRICT.items():
        district_mapping[neighborhood.lower().strip()] = district
        # Also add without spaces
        district_mapping[neighborhood.lower().replace(' ', '').strip()] = district
    
    # Add direct district name matches from GeoJSON
    for feature in districts_geojson['features']:
        district_name = feature['properties']['District']
        # Direct lowercase match
        district_mapping[district_name.lower()] = district_name
        # No-spaces match
        district_mapping[district_name.replace(' ', '').lower()] = district_name
        # Handle "&" vs "and" (e.g., "Central & Western" vs "central and western")
        district_mapping[district_name.lower().replace('&', 'and')] = district_name
        district_mapping[district_name.lower().replace('&', 'and').replace(' ', '')] = district_name
    
    return district_mapping


def normalize_district_name(district: str, mapping: Dict[str, str]) -> str:
    """
    Normalize district name to match GeoJSON official district names.
    
    Args:
        district: Input district/neighborhood name from CSV
        mapping: District name mapping from load_district_mapping()
    
    Returns:
        Official district name or original if not found
    """
    if pd.isna(district):
        return district
    
    name = str(district).strip().lower()
    
    # Direct lookup
    if name in mapping:
        return mapping[name]
    
    # Try without spaces
    no_spaces = name.replace(' ', '')
    if no_spaces in mapping:
        return mapping[no_spaces]
    
    # Try replacing common variations
    for replacement in ['&', 'and', '-']:
        variant = name.replace(replacement, ' ')
        if variant in mapping:
            return mapping[variant]
        no_space_variant = variant.replace(' ', '')
        if no_space_variant in mapping:
            return mapping[no_space_variant]
    
    # No match found - return original (will show as unmatched)
    return district


def aggregate_water_quality(df: pd.DataFrame, 
                             geojson_path: str, 
                             parameter_name: str) -> pd.DataFrame:
    """
    Aggregate water quality data by district.
    
    Maps CSV neighborhood names to the 18 HK administrative districts,
    then aggregates water quality results by district.
    
    Args:
        df: Input DataFrame with water quality data
        geojson_path: Path to districts GeoJSON
        parameter_name: Parameter being analyzed (cl2_free_1, ecoli, turby)
    
    Returns:
        DataFrame with district-level aggregations
    """
    # Load district name mapping
    district_mapping = load_district_mapping(geojson_path)
    
    # Normalize district names in the input DataFrame
    df['normalized_district'] = df['district'].apply(
        lambda x: normalize_district_name(str(x), district_mapping)
    )
    
    # Log unmatched districts
    unmatched = df[~df['normalized_district'].isin(
        set(district_mapping.values())
    )]['normalized_district'].unique()
    if len(unmatched) > 0:
        print(f"  [WARN] Unmatched districts: {list(unmatched)}")
    
    # Aggregation methods based on parameter type
    if 'cl2' in parameter_name.lower() or 'free' in parameter_name.lower():
        # Chlorine: mean and max
        district_stats = df.groupby('normalized_district')['result'].agg([
            ('mean', 'mean'), 
            ('max', 'max'), 
            ('count', 'count')
        ]).reset_index()
        district_stats['aggregation_method'] = 'Chlorine Levels (mg/L)'
    
    elif 'eco' in parameter_name.lower() or 'coli' in parameter_name.lower():
        # E. coli: percentage of contaminated samples
        # Use explicit column selection to avoid include_groups compatibility issues
        ecoli_df = df[['normalized_district', 'result']].copy()
        district_stats = ecoli_df.groupby('normalized_district').apply(
            lambda x: pd.Series({
                'contaminated_samples': (x['result'] > 0).sum(),
                'total_samples': len(x),
                'contamination_rate': (x['result'] > 0).mean() * 100,
                'mean': x['result'].mean(),
                'max': x['result'].max(),
                'count': len(x)
            })
        ).reset_index()
        district_stats['aggregation_method'] = 'E. coli Contamination'
    
    elif 'turb' in parameter_name.lower():
        # Turbidity: mean and max
        district_stats = df.groupby('normalized_district')['result'].agg([
            ('mean', 'mean'), 
            ('max', 'max'), 
            ('count', 'count')
        ]).reset_index()
        district_stats['aggregation_method'] = 'Turbidity Levels (NTU)'
    
    else:
        # Default to mean if parameter type is unclear
        district_stats = df.groupby('normalized_district')['result'].agg([
            ('mean', 'mean'), 
            ('max', 'max'), 
            ('count', 'count')
        ]).reset_index()
        district_stats['aggregation_method'] = 'Average Value'
    
    return district_stats

def get_color_for_district(value: float, parameter_name: str) -> str:
    """
    Determine color for district based on parameter type.
    
    The code logic uses continuous boundaries with no gaps.
    The legend display uses rounded boundaries (e.g., 1.6 instead of 1.5)
    for readability, but the actual thresholds here ensure every value
    falls into exactly one category.
    
    Args:
        value: Aggregated value for the district
        parameter_name: Parameter being analyzed
    
    Returns:
        Color representing water quality
    """
    if 'cl2' in parameter_name.lower() or 'free' in parameter_name.lower():
        # Chlorine color scale (WSD standard: 0.2-1.5 mg/L ideal range)
        # Red (insufficient): value < 0.2
        # Green (satisfactory): 0.2 <= value <= 1.5
        # Orange (slightly high): 1.5 < value <= 2.0
        # Darkred (high): 2.0 < value <= 3.0
        # Red (very high): value > 3.0
        if pd.isna(value):
            return 'gray'
        elif value < 0.2:
            return 'red'
        elif value <= 1.5:
            return 'green'
        elif value <= 2.0:
            return 'orange'
        elif value <= 3.0:
            return 'darkred'
        else:
            return 'red'
    
    elif 'eco' in parameter_name.lower() or 'coli' in parameter_name.lower():
        # E. coli color scale (CFU/100mL)
        # Green (satisfactory): value == 0
        # Red (unsatisfactory): value > 0
        if pd.isna(value):
            return 'gray'
        elif value == 0:
            return 'green'
        else:
            return 'red'
    
    elif 'turb' in parameter_name.lower():
        # Turbidity color scale (NTU)
        # Green (satisfactory): value <= 1.5
        # Orange (slightly high): 1.5 < value <= 3.0
        # Darkred (high): 3.0 < value <= 10.0
        # Red (very high): value > 10.0
        if pd.isna(value):
            return 'gray'
        elif value <= 1.5:
            return 'green'
        elif value <= 3.0:
            return 'orange'
        elif value <= 10.0:
            return 'darkred'
        else:
            return 'red'
    
    # Default color if parameter is unrecognized
    return 'gray'
