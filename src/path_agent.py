import overpy
import requests
import json

system_prompt = '''
You are a helpful assistant for processing OpenStreetMap data. 
Your goal is to determine from the prompt what sort of road types are suitable to be searched for.
Assume by default that they are traveling on foot or bicycle and thus should focus on pedestrian paths and bicycle paths.
You can also search for car roads if needed.
Here are the road types that you can use:
Car Roads:
primary - Major roads (like Crowchild Trail)
secondary - Important roads (like 17 Avenue)
tertiary - Local connector roads
residential - Neighborhood streets
trunk - Highway-like roads
motorway - Highways/freeways
unclassified - Minor roads
service - Service roads, parking lots

Pedestrian Paths:
footway - Sidewalks and walking paths
path - General paths (walking/hiking)
pedestrian - Pedestrian-only areas
steps - Stairs and steps

Bicycle Paths:
cycleway - Dedicated bike lanes/paths

It is okay to combine these road types in a single query.
Return a json object with the following structure:
{
  "roads": ["primary", "footway", "cycleway"]
}
'''

class PathAgent:
    def __init__(self):
        self.api = overpy.Overpass()
        
    def get_bike_friendly_route(self, start_lat, start_lon, end_lat, end_lon, avoid_highways=True, save_filename=None):
        """Get a bicycle-friendly route avoiding highways"""
        
        if avoid_highways:
            # Use bike-specific routing profile and exclude highways
            osrm_url = f"http://localhost:5000/route/v1/bicycle/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson"
        else:
            osrm_url = f"http://localhost:5000/route/v1/bicycle/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson"
        
        try:
            response = requests.get(osrm_url)
            route_data = response.json()
            
            # Convert to GeoJSON and save using utils only if filename provided
            if route_data and 'routes' in route_data and route_data['routes'] and save_filename:
                self._save_route_as_geojson(route_data, save_filename)
            
            return route_data
        except Exception as e:
            print(f"Error getting route: {e}")
            return None
    
    def analyze_route_for_highways(self, coordinates, sample_every=20):
        """Check if route contains highways or unwanted road types"""
        highways_found = []
        
        for i, coord in enumerate(coordinates[::sample_every]):
            lon, lat = coord[0], coord[1]
            
            # Small bounding box around coordinate
            buffer = 0.001
            query = f"""
            [out:json][timeout:10];
            (
              way["highway"]({lat-buffer},{lon-buffer},{lat+buffer},{lon+buffer});
            );
            out tags;
            """
            
            try:
                result = self.api.query(query)
                for way in result.ways:
                    highway_type = way.tags.get('highway', 'unknown')
                    if highway_type in ['motorway', 'trunk', 'primary']:
                        highways_found.append({
                            'way_id': way.id,
                            'name': way.tags.get('name', 'Unnamed'),
                            'highway_type': highway_type,
                            'coordinate': (lat, lon),
                            'point_index': i * sample_every
                        })
                        break  # One highway per sample point is enough
            except:
                continue
        
        return highways_found
    
    def create_detour_waypoints(self, start_lat, start_lon, end_lat, end_lon, highways_to_avoid):
        """Create waypoints to route around identified highways"""
        waypoints = [(start_lat, start_lon)]
        
        if highways_to_avoid:
            # Simple detour strategy: offset perpendicular to highway direction
            for highway in highways_to_avoid[:2]:  # Limit to first 2 highways
                hw_lat, hw_lon = highway['coordinate']
                
                # Create offset points to go around the highway
                lat_offset = 0.005  # ~500m offset
                lon_offset = 0.005
                
                # Try different offset directions
                detour_points = [
                    (hw_lat + lat_offset, hw_lon),
                    (hw_lat - lat_offset, hw_lon),
                    (hw_lat, hw_lon + lon_offset),
                    (hw_lat, hw_lon - lon_offset)
                ]
                
                # Add the best detour point (you could improve this logic)
                waypoints.append(detour_points[0])
        
        waypoints.append((end_lat, end_lon))
        return waypoints
    
    def get_route_with_waypoints(self, waypoints, save_filename=None):
        """Get route through multiple waypoints"""
        if len(waypoints) < 2:
            return None
        
        # Format waypoints for OSRM
        coord_string = ";".join([f"{lon},{lat}" for lat, lon in waypoints])
        osrm_url = f"http://localhost:5000/route/v1/bicycle/{coord_string}?overview=full&geometries=geojson"
        
        try:
            response = requests.get(osrm_url)
            route_data = response.json()
            
            # Convert to GeoJSON and save using utils only if filename provided
            if route_data and 'routes' in route_data and route_data['routes'] and save_filename:
                self._save_route_as_geojson(route_data, save_filename)
            
            return route_data
        except Exception as e:
            print(f"Error getting waypoint route: {e}")
            return None
    
    def smart_reroute(self, start_lat, start_lon, end_lat, end_lon, max_attempts=3, save_filename=None):
        """Intelligent rerouting that avoids highways"""
        
        print("🚴 Getting initial bicycle route...")
        route = self.get_bike_friendly_route(start_lat, start_lon, end_lat, end_lon, avoid_highways=True)
        print(f"Initial route response: {route}")
        if not route or 'routes' not in route or not route['routes']:
            print("❌ No initial route found")
            return None

        coordinates = route['routes'][0]['geometry']['coordinates']
        distance = route['routes'][0]['distance']
        duration = route['routes'][0]['duration']
        
        print(f"📊 Initial route: {distance/1000:.2f}km, {duration/60:.1f}min")
        
        # Check for highways in the route
        print("🔍 Checking for highways...")
        highways = self.analyze_route_for_highways(coordinates)
        
        if not highways:
            print("✅ No highways found in route!")
            # Save if filename provided
            if save_filename:
                self._save_route_as_geojson(route, save_filename)
            return route
        
        print(f"⚠️  Found {len(highways)} highway segments:")
        for hw in highways:
            print(f"   - {hw['name']} ({hw['highway_type']})")
        
        # Attempt rerouting with waypoints
        for attempt in range(max_attempts):
            print(f"\n🔄 Rerouting attempt {attempt + 1}...")
            
            waypoints = self.create_detour_waypoints(start_lat, start_lon, end_lat, end_lon, highways)
            new_route = self.get_route_with_waypoints(waypoints)
            
            if new_route and 'routes' in new_route and new_route['routes']:
                new_coordinates = new_route['routes'][0]['geometry']['coordinates']
                new_distance = new_route['routes'][0]['distance']
                new_duration = new_route['routes'][0]['duration']
                
                print(f"📊 New route: {new_distance/1000:.2f}km, {new_duration/60:.1f}min")
                
                # Check if new route still has highways
                new_highways = self.analyze_route_for_highways(new_coordinates)
                
                if len(new_highways) < len(highways):
                    print(f"✅ Improved! Reduced highways from {len(highways)} to {len(new_highways)}")
                    # Save if filename provided
                    if save_filename:
                        self._save_route_as_geojson(new_route, save_filename)
                    return new_route
                else:
                    print(f"❌ Still has {len(new_highways)} highway segments")
                    # Update highways list for next attempt
                    highways = new_highways
    
        print("⚠️  Could not completely avoid highways, returning best attempt")
        # Save the final route if filename provided
        if save_filename:
            self._save_route_as_geojson(route, save_filename)
    
        return route

    def _save_route_as_geojson(self, route, filename):
        """Helper method to save route as GeoJSON"""
        try:
            if route and 'routes' in route and route['routes']:
                from utils import osrm_route_to_geojson
                
                # Convert to GeoJSON
                geojson = osrm_route_to_geojson(route)
                
                # Save to specified filename
                import json
                with open(filename, 'w') as f:
                    json.dump(geojson, f, indent=2)
                
                print(f"💾 Route saved to {filename}")
        except Exception as e:
            print(f"❌ Error saving route to {filename}: {e}")

# Example usage function
def plan_route_avoiding_highways():
    """Example of using the detour agent"""
    agent = PathAgent()
    
    # Example: Calgary coordinates
    start_lat, start_lon = 51.044261, -114.224639
    end_lat, end_lon = 51.040365, -114.209501
    
    print("🚴 Planning bicycle route avoiding highways...")
    print(f"📍 From: ({start_lat}, {start_lon})")
    print(f"📍 To: ({end_lat}, {end_lon})")
    print("=" * 60)
    
    route = agent.smart_reroute(start_lat, start_lon, end_lat, end_lon, "path_agent.json")
    agent._save_route_as_geojson(route, "path_agent_test.json")
    if route and 'routes' in route:
        coordinates = route['routes'][0]['geometry']['coordinates']
        distance = route['routes'][0]['distance']
        duration = route['routes'][0]['duration']
        
        print(f"\n🎯 FINAL ROUTE:")
        print(f"📏 Distance: {distance/1000:.2f} km")
        print(f"⏱️  Duration: {duration/60:.1f} minutes")
        print(f"📍 Waypoints: {len(coordinates)}")
        
        # Show route on map (first few coordinates)
        print(f"\n🗺️  Route preview:")
        for i, coord in enumerate(coordinates[:3]):
            print(f"   {i+1}: {coord[1]:.6f}, {coord[0]:.6f}")
        if len(coordinates) > 3:
            print(f"   ... ({len(coordinates)-3} more points)")
    
    return route

# Run the example
if __name__ == "__main__":
    plan_route_avoiding_highways()