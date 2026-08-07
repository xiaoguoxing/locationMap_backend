import os
import pandas as pd
import folium
from folium.plugins import MarkerCluster

# File path
csv_path = "bp_data.csv"

# Check if file exists
if not os.path.exists(csv_path):
    print(f"❌ ERROR: '{csv_path}' not found in current directory.")
    print("💡 Please place it here:", os.getcwd())
    exit(1)

print("✅ CSV file found. Loading data...")

# Load data
try:
    df = pd.read_csv(csv_path)
    print(f"📈 Loaded {len(df)} rows.")
except Exception as e:
    print("❌ Error reading CSV:", e)
    exit(1)

# Clean column names (remove extra spaces, lowercase)
# df.columns = df.columns.str.strip().str.lower()
df.columns = df.columns.str.replace(r'\s+', ' ', regex=True).str.strip().str.lower()


# Ensure required columns exist
required_cols = ['lat', 'lon', 'case_id', 'location_desc', 'report_date']
missing = [col for col in required_cols if col not in df.columns]
if missing:
    print(f"❌ Missing required columns: {missing}")
    exit(1)

# Drop rows with missing lat/lon
df = df.dropna(subset=['lat', 'lon'])
print(f"✅ {len(df)} valid points with coordinates.")

if len(df) == 0:
    print("⚠️ No valid location data to display.")
    exit(1)

# Compute map center
center_lat = df['lat'].mean()
center_lon = df['lon'].mean()

# Create map
m = folium.Map(location=[center_lat, center_lon], zoom_start=12)

# Add marker cluster
marker_cluster = MarkerCluster().add_to(m)

# Add markers
for _, row in df.iterrows():
    popup_text = (
        f"<b>Case ID:</b> {row['case_id']}<br>"
        f"<b>Location:</b> {row['location_desc']}<br>"
        f"<b>Reported:</b> {row['report_date']}"
    )
    folium.Marker(
        location=[row['lat'], row['lon']],
        popup=popup_text,
        icon=folium.Icon(color='black', icon='exclamation-triangle', prefix='fa')
    ).add_to(marker_cluster)

# Save to HTML
output_file = "blackspot_map.html"
m.save(output_file)
print(f"✅ Map saved as '{output_file}'")
print(f"👉 Open it: file:///{os.path.abspath(output_file).replace(chr(92), '/')}")
