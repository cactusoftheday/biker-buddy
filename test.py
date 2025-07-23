import overpy

# Initialize Overpass API
api = overpy.Overpass()

# Query for both car roads and pedestrian paths using your coordinates
# Assuming order: lat1, lon1, lon2, lat2 -> converting to (south, west, north, east)
query = """
[out:json][timeout:25];
(
  way["highway"~"^(primary|secondary|tertiary|residential|trunk|motorway|unclassified|service|footway|path|pedestrian|cycleway|steps)$"](51.096707,-114.166789,51.099591,-114.158367);
);
out geom;
"""

# Run the query
result = api.query(query)

# Print results
print(f"Found {len(result.ways)} road and pedestrian segments")
print("=" * 50)

# Filter and print ALL cycleways
cycleways = [way for way in result.ways if way.tags.get('highway') == 'cycleway']

print(f"\n🚴 FOUND {len(cycleways)} CYCLEWAYS:")
print("=" * 80)

for i, way in enumerate(cycleways):
    name = way.tags.get('name', 'Unnamed')
    highway_type = way.tags.get('highway', 'unknown')
    lanes = way.tags.get('lanes', 'unknown')
    maxspeed = way.tags.get('maxspeed', 'unknown')
    surface = way.tags.get('surface', 'unknown')
    access = way.tags.get('access', 'unknown')
    foot = way.tags.get('foot', 'unknown')
    bicycle = way.tags.get('bicycle', 'unknown')
    width = way.tags.get('width', 'unknown')
    segregated = way.tags.get('segregated', 'unknown')
    cycleway_type = way.tags.get('cycleway', 'unknown')
    
    print(f"\n🚴 Cycleway {i+1}: {name}")
    print(f"  Highway type: {highway_type}")
    print(f"  Cycleway type: {cycleway_type}")
    print(f"  Width: {width}")
    print(f"  Surface: {surface}")
    print(f"  Segregated: {segregated}")
    print(f"  Foot access: {foot}")
    print(f"  Access: {access}")
    print(f"  Way ID: {way.id}")
    
    # Show coordinate information for mapping
    try:
        if hasattr(way, 'nd') and way.nd and len(way.nd) > 0:
            print(f"  Number of nodes: {len(way.nd)}")
            print(f"  Start: ({way.nd[0].lat}, {way.nd[0].lon})")
            print(f"  End: ({way.nd[-1].lat}, {way.nd[-1].lon})")
            
            # Calculate center point for easy mapping
            center_lat = sum(float(node.lat) for node in way.nd) / len(way.nd)
            center_lon = sum(float(node.lon) for node in way.nd) / len(way.nd)
            print(f"  Center: ({center_lat:.5f}, {center_lon:.5f})")
            
            # Provide direct links for mapping
            print(f"  📍 OpenStreetMap: https://openstreetmap.org/way/{way.id}")
            print(f"  🗺️  Google Maps: https://maps.google.com/?q={center_lat},{center_lon}")
            
        else:
            print(f"  No coordinate data available")
            print(f"  📍 OpenStreetMap: https://openstreetmap.org/way/{way.id}")
            
    except Exception as e:
        print(f"  Error processing coordinates: {e}")
        print(f"  📍 OpenStreetMap: https://openstreetmap.org/way/{way.id}")
    
    print("-" * 80)

# Show first 5 segments for demonstration (original code)
print(f"\n📋 FIRST 5 SEGMENTS (ALL TYPES):")
print("=" * 50)

for i, way in enumerate(result.ways[:5]):
    name = way.tags.get('name', 'Unnamed')
    highway_type = way.tags.get('highway', 'unknown')
    lanes = way.tags.get('lanes', 'unknown')
    maxspeed = way.tags.get('maxspeed', 'unknown')
    surface = way.tags.get('surface', 'unknown')
    access = way.tags.get('access', 'unknown')
    foot = way.tags.get('foot', 'unknown')
    bicycle = way.tags.get('bicycle', 'unknown')
    
    print(f"\nSegment {i+1}: {name}")
    print(f"  Highway type: {highway_type}")
    print(f"  Lanes: {lanes}")
    print(f"  Speed limit: {maxspeed}")
    print(f"  Surface: {surface}")
    print(f"  Access: {access}")
    print(f"  Foot access: {foot}")
    print(f"  Bicycle access: {bicycle}")
    print(f"  Way ID: {way.id}")
    
    # Categorize road type
    car_roads = ['primary', 'secondary', 'tertiary', 'residential', 'trunk', 'motorway', 'unclassified', 'service']
    pedestrian_roads = ['footway', 'path', 'pedestrian', 'steps']
    bike_roads = ['cycleway']
    
    if highway_type in car_roads:
        road_category = "🚗 Car Road"
    elif highway_type in pedestrian_roads:
        road_category = "🚶 Pedestrian Path"
    elif highway_type in bike_roads:
        road_category = "🚴 Cycle Path"
    else:
        road_category = "❓ Other"
    
    print(f"  Category: {road_category}")
    
    # Show coordinate information for mapping
    try:
        if hasattr(way, 'nd') and way.nd and len(way.nd) > 0:
            print(f"  Number of nodes: {len(way.nd)}")
            print(f"  Start: ({way.nd[0].lat}, {way.nd[0].lon})")
            print(f"  End: ({way.nd[-1].lat}, {way.nd[-1].lon})")
            
            # Calculate center point for easy mapping
            center_lat = sum(float(node.lat) for node in way.nd) / len(way.nd)
            center_lon = sum(float(node.lon) for node in way.nd) / len(way.nd)
            print(f"  Center: ({center_lat:.5f}, {center_lon:.5f})")
            
            # Provide direct links for mapping
            print(f"  📍 OpenStreetMap: https://openstreetmap.org/way/{way.id}")
            print(f"  🗺️  Google Maps: https://maps.google.com/?q={center_lat},{center_lon}")
            
        else:
            print(f"  No coordinate data available")
            print(f"  📍 OpenStreetMap: https://openstreetmap.org/way/{way.id}")
            
    except Exception as e:
        print(f"  Error processing coordinates: {e}")
        print(f"  📍 OpenStreetMap: https://openstreetmap.org/way/{way.id}")
    
    print("-" * 50)

# Summary statistics
car_count = sum(1 for way in result.ways if way.tags.get('highway') in ['primary', 'secondary', 'tertiary', 'residential', 'trunk', 'motorway', 'unclassified', 'service'])
pedestrian_count = sum(1 for way in result.ways if way.tags.get('highway') in ['footway', 'path', 'pedestrian', 'steps'])
cycle_count = sum(1 for way in result.ways if way.tags.get('highway') in ['cycleway'])

print(f"\n📊 SUMMARY:")
print(f"🚗 Car roads: {car_count}")
print(f"🚶 Pedestrian paths: {pedestrian_count}")
print(f"🚴 Cycle paths: {cycle_count}")
print(f"📍 Total segments: {len(result.ways)}")
