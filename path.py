import overpy
import requests

# Step 1: Use Overpy to get coordinates
api = overpy.Overpass()

# Better query to find Safeway stores in Calgary
result = api.query("""
[out:json][timeout:25];
(
  node["shop"="supermarket"]["name"~"Safeway"](51.0,-114.3,51.2,-113.9);
  way["shop"="supermarket"]["name"~"Safeway"](51.0,-114.3,51.2,-113.9);
);
out center;
""")

print(f"Found {len(result.nodes)} Safeway nodes and {len(result.ways)} Safeway ways")

# Check if we found any results
if result.nodes:
    safeway = result.nodes[0]
    lat1, lon1 = float(safeway.lat), float(safeway.lon)
    print(f"Using Safeway at: {lat1}, {lon1}")
elif result.ways:
    safeway = result.ways[0]
    lat1, lon1 = float(safeway.center_lat), float(safeway.center_lon)
    print(f"Using Safeway at: {lat1}, {lon1}")
else:
    # Fallback to a known Safeway location in Calgary
    print("No Safeway found, using known location")
    lat1, lon1 = 51.0431, -114.0719  # Safeway in Kensington
    print(f"Using fallback Safeway at: {lat1}, {lon1}")

# Hardcoded destination (e.g., Shoppers)
lat2, lon2 = 51.042, -114.208

print(f"Route from ({lat1}, {lon1}) to ({lat2}, {lon2})")

# Step 2: Use OSRM to get the route
osrm_url = f"http://router.project-osrm.org/route/v1/bicycle/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"

try:
    response = requests.get(osrm_url)
    route = response.json()
    print(route)
    
    if 'routes' in route and len(route['routes']) > 0:
        coordinates = route['routes'][0]['geometry']['coordinates']
        distance = route['routes'][0]['distance']  # in meters
        duration = route['routes'][0]['duration']  # in seconds
        
        print(f"Route distance: {distance/1000:.2f} km")
        print(f"Duration: {duration/60:.1f} minutes")
        print(f"Number of coordinate points: {len(coordinates)}")
        
        # Show first few coordinates for verification
        print("First 3 coordinates:")
        for i, coord in enumerate(coordinates[:3]):
            print(f"  {i+1}: lon={coord[0]:.6f}, lat={coord[1]:.6f}")
            
    else:
        print("No route found")
        print("OSRM Response:", route)
        
except Exception as e:
    print(f"Error getting route: {e}")
    print(f"URL used: {osrm_url}")
