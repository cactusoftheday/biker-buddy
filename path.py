import overpy
import requests
from src.utils import osrm_route_to_geojson
import json
lat1, lon1 = 51.042933, -114.223255
# Hardcoded destination (e.g., Shoppers)
lat2, lon2 = 51.04227551463415, -114.21670761951219

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
        
        # Use the osrm_route_to_geojson function from utils
        geojson = osrm_route_to_geojson(route)
        
        with open("path.json", "w") as f:
            json.dump(geojson, f, indent=2)
        print("GeoJSON route saved to path.json")
        
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
