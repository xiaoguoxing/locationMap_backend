#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Water Quality Map Dashboard - Flask Backend
Serves API endpoints and static files for the dashboard
"""

import os
import re
import json
from pathlib import Path
from datetime import datetime
from flask import Flask, jsonify, render_template, send_from_directory, request

# Create Flask app
app = Flask(__name__)

# Configuration
# Use absolute path based on this file's location
MAPS_OUTPUT_DIR = Path(__file__).parent.parent / 'maps' / 'output'

# Parameter metadata for display
PARAMETER_INFO = {
    'cl2_free_1': {
        'display_name': 'Free Chlorine',
        'unit': 'mg/L'
    },
    'ecoli': {
        'display_name': 'E. coli',
        'unit': 'CFU/100mL'
    },
    'turby': {
        'display_name': 'Turbidity',
        'unit': 'NTU'
    },
    'all_params': {
        'display_name': 'All Parameters',
        'unit': 'Multi'
    }
}


def parse_filename(filename):
    """
    Parse map filename to extract metadata
    
    Supported patterns:
    - {parameter}_{date_from}_{date_to}_{timestamp}_map.html
    - {parameter}_{timestamp}_map.html (legacy, no date range)
    
    Args:
        filename: Map filename (e.g., 'cl2_free_1_2025-10-19_2025-11-01_20260327_184448_map.html')
        
    Returns:
        dict: Parsed metadata or None if parsing fails
    """
    try:
        # Remove extension and _map/_district_map/_detailed_map suffix
        if '_district_map.html' in filename:
            base_name = filename.replace('_district_map.html', '')
        elif '_detailed_map.html' in filename:
            base_name = filename.replace('_detailed_map.html', '')
        else:
            base_name = filename.replace('_map.html', '')
        
        # Split by underscores
        parts = base_name.split('_')
        
        # Look for date pattern (YYYY-MM-DD) to find parameter end
        date_idx = None
        for i, part in enumerate(parts):
            if re.match(r'\d{4}-\d{2}-\d{2}', part):
                date_idx = i
                break
        
        if date_idx:
            # New format with date range: {parameter}_{date_from}_{date_to}_{timestamp}
            parameter = '_'.join(parts[:date_idx])
            date_from = parts[date_idx]
            date_to = parts[date_idx + 1] if (date_idx + 1) < len(parts) else None
            timestamp = '_'.join(parts[date_idx + 2:]) if (date_idx + 2) < len(parts) else None
        else:
            # Legacy format without date range: {parameter}_{timestamp}
            parameter = parts[0]
            timestamp = '_'.join(parts[1:]) if len(parts) > 1 else None
            date_from = None
            date_to = None
        
        # Get parameter metadata
        param_info = PARAMETER_INFO.get(parameter, {
            'display_name': parameter,
            'unit': ''
        })
        
        # Format date range for display
        if date_from and date_to:
            date_range = f"{date_from} to {date_to}"
        else:
            date_range = None
        
        # Determine view_type based on parameter
        if parameter == 'all_params':
            view_type = 'district_all_param'
        else:
            # Determine from filename suffix
            if '_district_map.html' in filename:
                view_type = 'district'
            elif '_detailed_map.html' in filename:
                view_type = 'detailed'
            else:
                view_type = 'district'
        
        # Build URL path
        url = f"/maps/output/{view_type}/{filename}"
        
        return {
            'filename': filename,
            'parameter': parameter,
            'display_name': param_info['display_name'],
            'unit': param_info['unit'],
            'date_from': date_from,
            'date_to': date_to,
            'date_range': date_range,
            'timestamp': timestamp,
            'url': url,
            'view_type': view_type
        }
        
    except Exception as e:
        print(f"Error parsing filename {filename}: {e}")
        return None


def scan_maps_directory():
    """
    Scan the maps/output directory and parse all map files
    
    Scans district, district_all_param, and detailed subdirectories.
    
    Returns:
        list: List of parsed map metadata dictionaries
    """
    maps = []
    
    # Scan the district subdirectory (single-parameter district maps)
    district_dir = MAPS_OUTPUT_DIR / 'district'
    if district_dir.exists():
        for map_file in district_dir.glob('*_map.html'):
            metadata = parse_filename(map_file.name)
            if metadata:
                maps.append(metadata)
    
    # Scan the district_all_param subdirectory (multi-parameter maps)
    all_param_dir = MAPS_OUTPUT_DIR / 'district_all_param'
    if all_param_dir.exists():
        for map_file in all_param_dir.glob('*_map.html'):
            metadata = parse_filename(map_file.name)
            if metadata:
                maps.append(metadata)
    
    # Scan the detailed subdirectory (point-based location maps)
    detailed_dir = MAPS_OUTPUT_DIR / 'detailed'
    if detailed_dir.exists():
        for map_file in detailed_dir.glob('*_map.html'):
            metadata = parse_filename(map_file.name)
            if metadata:
                maps.append(metadata)
    
    if not maps:
        print("Warning: No map files found in any maps/output subdirectory")
    
    # Sort maps by date (newest first), then by timestamp
    def sort_key(m):
        if m['date_from']:
            try:
                return (datetime.strptime(m['date_from'], '%Y-%m-%d'), m['timestamp'] or '')
            except ValueError:
                pass
        return (datetime.min, m['timestamp'] or '')
    
    maps.sort(key=sort_key, reverse=True)
    
    return maps


@app.route('/')
def index():
    """Render the main dashboard page"""
    return render_template('dashboard.html')


@app.route('/api/maps')
def api_maps():
    """
    API endpoint to get all available maps with metadata
    
    Returns JSON response with:
    - success: boolean
    - data: list of map metadata
    - summary: statistics about available maps
    """
    try:
        maps = scan_maps_directory()
        
        # Calculate summary statistics
        parameters = {}
        dates = []
        
        for m in maps:
            # Count by parameter
            param = m['parameter']
            parameters[param] = parameters.get(param, 0) + 1
            
            # Collect dates
            if m['date_from']:
                dates.append(m['date_from'])
        
        summary = {
            'total_maps': len(maps),
            'parameters': parameters,
            'date_range': {
                'earliest': min(dates) if dates else None,
                'latest': max(dates) if dates else None
            }
        }
        
        return jsonify({
            'success': True,
            'data': maps,
            'summary': summary
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'data': [],
            'summary': {
                'total_maps': 0,
                'parameters': {},
                'date_range': {'earliest': None, 'latest': None}
            }
        }), 500


@app.route('/maps/output/<path:filename>')
def serve_map(filename):
    """
    Serve static map HTML files from the maps/output directory (legacy support)
    
    This route allows the dashboard to load map HTML files via iframe
    """
    maps_dir = MAPS_OUTPUT_DIR
    
    if not maps_dir.exists():
        return jsonify({'error': 'Maps directory not found'}), 404
    
    try:
        return send_from_directory(maps_dir, filename)
    except FileNotFoundError:
        return jsonify({'error': f'Map file not found: {filename}'}), 404


@app.route('/maps/output/<view_type>/<path:filename>')
def serve_map_with_view_type(view_type, filename):
    """
    Serve static map HTML files from the maps/output subdirectories
    
    Args:
        view_type: 'district', 'detailed', or 'district_all_param'
        filename: Map filename
    
    This route allows the dashboard to load map HTML files via iframe
    with separate directories for district, detailed, and all-params views
    """
    maps_dir = MAPS_OUTPUT_DIR / view_type
    
    if not maps_dir.exists():
        return jsonify({'error': f'Maps directory not found: {view_type}'}), 404
    
    try:
        return send_from_directory(maps_dir, filename)
    except FileNotFoundError:
        return jsonify({'error': f'Map file not found: {filename}'}), 404


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'API endpoint not found'}), 404
    return render_template('404.html'), 404


if __name__ == '__main__':
    print("=" * 70)
    print("Water Quality Map Dashboard Server")
    print("=" * 70)
    print(f"\nMaps directory: {MAPS_OUTPUT_DIR.absolute()}")
    print(f"API endpoint: http://localhost:5000/api/maps")
    print(f"Dashboard: http://localhost:5000")
    print("\nPress CTRL+C to stop the server")
    print("=" * 70)
    
    # Run Flask app
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        threaded=True
    )
