#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from app import app

with app.test_client() as client:
    print("Testing /api/maps endpoint...")
    response = client.get('/api/maps')
    print(f"Status: {response.status_code}")
    
    data = response.get_json()
    print(f"Success: {data.get('success')}")
    print(f"Maps found: {len(data.get('data', []))}")
    print(f"Summary: {data.get('summary')}")
    
    if data.get('data'):
        print("\nFirst map:")
        print(f"  Filename: {data['data'][0]['filename']}")
        print(f"  Parameter: {data['data'][0]['parameter']}")
        print(f"  Date range: {data['data'][0]['date_range']}")
