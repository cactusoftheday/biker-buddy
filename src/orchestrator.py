import json
import os
from typing import Dict, List, Any, Optional
from utils import chat_with_openai
from route_agent import RouteAnalysisAgent
from path_agent import PathAgent
import dotenv

dotenv.load_dotenv()

class RouteOrchestrator:
    def __init__(self, openai_api_key: str):
        self.openai_api_key = openai_api_key
        self.route_agent = RouteAnalysisAgent(openai_api_key)
        self.path_agent = PathAgent()
        
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "create_route",
                    "description": "Create a bicycle or pedestrian route between two points, optionally avoiding highways",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "start_lat": {"type": "number", "description": "Starting latitude"},
                            "start_lon": {"type": "number", "description": "Starting longitude"},
                            "end_lat": {"type": "number", "description": "Ending latitude"},
                            "end_lon": {"type": "number", "description": "Ending longitude"},
                            "avoid_highways": {"type": "boolean", "description": "Whether to avoid highways (default true for bikes/pedestrians)"},
                            "transport_mode": {"type": "string", "enum": ["bicycle", "foot"], "description": "Mode of transportation"}
                        },
                        "required": ["start_lat", "start_lon", "end_lat", "end_lon"]
                    }
                }
            },
            {
                "type": "function", 
                "function": {
                    "name": "analyze_route_for_amenities",
                    "description": "Analyze an existing route for nearby amenities and detour opportunities",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "geojson_file": {"type": "string", "description": "Path to the GeoJSON route file"},
                            "sample_distance_m": {"type": "number", "description": "Distance between sampling points in meters (default 300)"},
                            "detour_radius_m": {"type": "number", "description": "Radius to search for detours in meters (default 200)"}
                        },
                        "required": ["geojson_file"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "save_route_to_file",
                    "description": "Save a route to a GeoJSON file for later analysis",
                    "parameters": {
                        "type": "object", 
                        "properties": {
                            "route_data": {"type": "object", "description": "Route data from OSRM"},
                            "filename": {"type": "string", "description": "Filename to save to (default: route.json)"}
                        },
                        "required": ["route_data"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "find_detour_point",
                    "description": "Find a specific amenity or point along a route for creating a detour",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "geojson_file": {"type": "string", "description": "Path to the route GeoJSON file"},
                            "amenity_type": {"type": "string", "description": "Type of amenity to find (e.g., 'cafe', 'restaurant', 'atm')"},
                            "amenity_name": {"type": "string", "description": "Optional specific name of amenity"},
                            "max_detour_distance": {"type": "number", "description": "Maximum detour distance in meters (default 300)"}
                        },
                        "required": ["geojson_file", "amenity_type"]
                    }
                }
            },
            {
                "type": "function", 
                "function": {
                    "name": "create_detour_route",
                    "description": "Create a route with a detour by combining two separate routes",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "start_lat": {"type": "number", "description": "Starting latitude"},
                            "start_lon": {"type": "number", "description": "Starting longitude"}, 
                            "detour_lat": {"type": "number", "description": "Detour point latitude"},
                            "detour_lon": {"type": "number", "description": "Detour point longitude"},
                            "end_lat": {"type": "number", "description": "Final destination latitude"},
                            "end_lon": {"type": "number", "description": "Final destination longitude"},
                            "transport_mode": {"type": "string", "enum": ["bicycle", "foot"], "description": "Mode of transportation"}
                        },
                        "required": ["start_lat", "start_lon", "detour_lat", "detour_lon", "end_lat", "end_lon"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_route_for_specific_amenities",
                    "description": "Analyze a route for specific types of amenities based on user needs. First calls general analysis, then filters for specific amenity types.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "geojson_file": {"type": "string", "description": "Path to the GeoJSON route file"},
                            "amenity_types": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Specific amenity types to look for (e.g., ['restaurant', 'cafe', 'toilets', 'bank', 'park'])"
                            },
                            "sample_distance_m": {"type": "number", "description": "Distance between sampling points in meters (default 300)"},
                            "detour_radius_m": {"type": "number", "description": "Radius to search for detours in meters (default 200)"}
                        },
                        "required": ["geojson_file", "amenity_types"]
                    }
                }
            }
        ]
        
        self.system_prompt = """
You are a smart route planning assistant specialized in creating bicycle and pedestrian routes. 
Your goal is to help users create the best possible route that meets their needs.

Key priorities:
1. Safety first - prioritize bike lanes, cycleways, and pedestrian paths
2. User satisfaction - meet their specific needs even if it requires longer detours
3. Minimize unnecessary detours - be efficient when possible
4. Consider amenities - help users find food, water, restrooms, bike shops along the route

For cyclists, prioritize:
- Dedicated cycleways and bike lanes
- Quiet residential streets
- Paths and trails
- Avoid busy roads and highways

For pedestrians, prioritize:
- Sidewalks and footways
- Pedestrian areas
- Parks and paths
- Safe crossings

When users ask for routes:
1. First create a basic route between their points
2. If they want amenity information:
   - For general amenities: use `analyze_route_for_amenities`
   - For specific needs: use `analyze_route_for_specific_amenities` and specify exactly which amenity types you want to find

IMPORTANT: When using `analyze_route_for_specific_amenities`:
- YOU choose which specific amenity types to look for based on the user's request
- Use specific amenity type names like: 'restaurant', 'cafe', 'toilets', 'bank', 'atm', 'park', 'pharmacy', 'bicycle_repair_station'
- The system will search the full amenities database and return only the types you specified
- Be specific - if user wants "food", specify ['restaurant', 'cafe', 'fast_food']
- If user wants "bike services", specify ['bicycle_repair_station', 'bicycle_parking', 'bicycle_rental']

Examples:
- User: "I need coffee" → use amenity_types: ['cafe']
- User: "I need food and a restroom" → use amenity_types: ['restaurant', 'cafe', 'fast_food', 'toilets']
- User: "Find parks and tourist spots" → use amenity_types: ['park', 'viewpoint', 'attraction', 'museum']
- User: "I need to stop for money and gas" → use amenity_types: ['bank', 'atm', 'fuel']

Available tools:
- create_route: For basic point-to-point routing
- analyze_route_for_amenities: For general amenity overview (returns filtered summary)
- analyze_route_for_specific_amenities: For finding specific amenity types (you choose the types)
- find_detour_point: To find a specific amenity by name/type
- create_detour_route: To create a route with a detour to a specific point
- save_route_to_file: To save routes for later analysis

Be conversational and helpful. Ask clarifying questions if the user's needs aren't clear.
"""
    def _filter_and_summarize_amenities(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Filter and summarize amenity analysis to reduce size for AI processing"""
        
        if 'sampling_points' not in analysis:
            return analysis
        
        # Categories to prioritize
        priority_categories = {
            'restaurant', 'cafe', 'fast_food', 'pub', 'bar',  # Food & Drink
            'bank', 'atm', 'pharmacy', 'hospital',  # Services
            'toilets', 'drinking_water', 'water_point', 'fountain',  # Necessities
            'bicycle_parking', 'bicycle_rental', 'bicycle_repair_station',  # Bike services
            'park', 'viewpoint', 'attraction', 'museum', 'gallery'  # Recreation
        }
        
        # Types to skip
        skip_types = {'bench', 'waste_basket', 'recycling', 'unknown'}
        
        summarized_points = []
        total_filtered_amenities = 0
        
        for point in analysis['sampling_points']:
            if 'detours' not in point or 'amenities' not in point['detours']:
                continue
                
            filtered_amenities = []
            
            for amenity in point['detours']['amenities']:
                # Skip if unnamed and not priority
                if (amenity['name'].startswith('Unnamed') and 
                    not any(cat in amenity['type'] for cat in priority_categories)):
                    continue
                    
                # Skip utility items
                if any(skip in amenity['type'] for skip in skip_types):
                    continue
                    
                # Skip if too far from route (>200m)
                if amenity['distance_from_route_m'] > 200:
                    continue
                    
                filtered_amenities.append({
                    'name': amenity['name'],
                    'type': amenity['type'],
                    'category': amenity['category'],
                    'brand': amenity.get('brand', ''),
                    'opening_hours': amenity.get('opening_hours', ''),
                    'distance_m': round(amenity['distance_from_route_m'], 1),
                    'location': amenity['location']
                })
            
            if filtered_amenities:
                # Group by category for summary
                category_counts = {}
                for amenity in filtered_amenities:
                    cat = amenity['category']
                    if cat not in category_counts:
                        category_counts[cat] = []
                    category_counts[cat].append(amenity)
                
                summarized_points.append({
                    'coordinate': point['coordinate'],
                    'amenity_summary': category_counts,
                    'total_nearby': len(filtered_amenities)
                })
                
                total_filtered_amenities += len(filtered_amenities)
        
        return {
            'route_info': analysis['route_info'],
            'total_relevant_amenities': total_filtered_amenities,
            'key_amenity_locations': summarized_points[:3],  # Limit to top 3 locations
            'summary': f"Found {total_filtered_amenities} relevant amenities along the route"
        }

    def _filter_amenities_by_user_needs(self, analysis: Dict[str, Any], user_needs: List[str]) -> Dict[str, Any]:
        """Filter amenities based on specific user needs/requests"""
        
        if 'sampling_points' not in analysis:
            return analysis
        
        # Map user needs to amenity categories
        need_to_categories = {
            # Food & Drink
            'food': {'restaurant', 'cafe', 'fast_food', 'pub', 'bar', 'bakery'},
            'coffee': {'cafe'},
            'restaurant': {'restaurant', 'fast_food', 'pub', 'bar'},
            'drink': {'pub', 'bar', 'cafe'},
            'eating': {'restaurant', 'cafe', 'fast_food', 'bakery'},
            
            # Services
            'money': {'bank', 'atm'},
            'bank': {'bank', 'atm'},
            'atm': {'atm'},
            'medical': {'pharmacy', 'hospital'},
            'pharmacy': {'pharmacy'},
            'gas': {'fuel'},
            'fuel': {'fuel'},
            
            # Necessities
            'water': {'drinking_water', 'water_point', 'fountain'},
            'toilet': {'toilets'},
            'restroom': {'toilets'},
            'bathroom': {'toilets'},
            
            # Bike services
            'bike': {'bicycle_parking', 'bicycle_rental', 'bicycle_repair_station', 'bicycle'},
            'parking': {'bicycle_parking'},
            'repair': {'bicycle_repair_station'},
            
            # Recreation
            'park': {'park', 'garden', 'nature_reserve'},
            'recreation': {'park', 'playground', 'sports_centre', 'swimming_pool'},
            'tourist': {'viewpoint', 'attraction', 'museum', 'gallery'},
            'shopping': {'convenience', 'supermarket', 'mall', 'shop'},
            
            # Default priorities (if no specific needs mentioned)
            'default': {'restaurant', 'cafe', 'fast_food', 'bank', 'atm', 'toilets', 
                       'drinking_water', 'bicycle_repair_station', 'park', 'viewpoint'}
        }
        
        # Determine which categories to include based on user needs
        target_categories = set()
        if not user_needs:
            target_categories = need_to_categories['default']
        else:
            for need in user_needs:
                need_lower = need.lower()
                for key, categories in need_to_categories.items():
                    if key in need_lower or need_lower in key:
                        target_categories.update(categories)
        
        # If no matches found, use default
        if not target_categories:
            target_categories = need_to_categories['default']
        
        summarized_points = []
        total_filtered_amenities = 0
        
        for point in analysis['sampling_points']:
            if 'detours' not in point or 'amenities' not in point['detours']:
                continue
                
            filtered_amenities = []
            
            for amenity in point['detours']['amenities']:
                # Check if amenity type matches any target categories
                amenity_type = amenity['type'].lower()
                matches_need = any(cat in amenity_type for cat in target_categories)
                
                if not matches_need:
                    continue
                    
                # Skip if too far from route (>250m for specific requests, >150m for general)
                max_distance = 250 if user_needs else 150
                if amenity['distance_from_route_m'] > max_distance:
                    continue
                    
                # Skip unnamed generic items unless they're high priority
                if (amenity['name'].startswith('Unnamed') and 
                    not any(priority in amenity_type for priority in ['restaurant', 'cafe', 'bank', 'atm', 'park'])):
                    continue
                    
                filtered_amenities.append({
                    'name': amenity['name'],
                    'type': amenity['type'],
                    'category': amenity['category'],
                    'brand': amenity.get('brand', ''),
                    'opening_hours': amenity.get('opening_hours', ''),
                    'distance_m': round(amenity['distance_from_route_m'], 1),
                    'location': amenity['location'],
                    'additional_info': amenity.get('additional_info', {})
                })
            
            if filtered_amenities:
                # Group by category for summary
                category_counts = {}
                for amenity in filtered_amenities:
                    cat = amenity['category']
                    if cat not in category_counts:
                        category_counts[cat] = []
                    category_counts[cat].append(amenity)
                
                summarized_points.append({
                    'coordinate': point['coordinate'],
                    'amenity_summary': category_counts,
                    'total_nearby': len(filtered_amenities)
                })
                
                total_filtered_amenities += len(filtered_amenities)
        
        return {
            'route_info': analysis['route_info'],
            'user_needs': user_needs,
            'target_categories': list(target_categories),
            'total_relevant_amenities': total_filtered_amenities,
            'key_amenity_locations': summarized_points[:5],  # Show more if specific request
            'summary': f"Found {total_filtered_amenities} relevant amenities for: {', '.join(user_needs) if user_needs else 'general needs'}"
        }

    def analyze_route_for_amenities(self, geojson_file: str, sample_distance_m: int = 300, 
                                  detour_radius_m: int = 200) -> Dict[str, Any]:
        """Analyze a route for amenities using the route agent"""
        try:
            print(f"🔍 Analyzing route {geojson_file} for amenities")
            
            analysis = self.route_agent.analyze_route(
                geojson_file, 
                sample_distance_m, 
                detour_radius_m
            )
            
            if 'error' in analysis:
                return {"success": False, "error": analysis['error']}
                
            # Filter and summarize the analysis for AI consumption
            filtered_analysis = self._filter_and_summarize_amenities(analysis)
            
            # Save the full analysis
            report_file = self.route_agent.save_analysis_report(analysis)
            # Save the filtered analysis as well
            filtered_report_file = os.path.splitext(geojson_file)[0] + "detour_opportunities_filter.json"
            with open(filtered_report_file, "w") as f:
                json.dump(filtered_analysis, f, indent=2)
            
            return {
                "success": True,
                "analysis": filtered_analysis,  # Return filtered version
                "full_report_file": report_file,  # Reference to full data
                "summary": {
                    "total_amenities": analysis['detour_summary']['amenity_detours'],
                    "relevant_amenities": filtered_analysis['total_relevant_amenities'],
                    "total_ways": analysis['detour_summary']['way_detours'],
                    "route_distance_km": analysis['route_info']['route_distance_km']
                }
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_route_with_waypoints(self, waypoints: List[Dict[str, Any]], 
                                  transport_mode: str = "bicycle") -> Dict[str, Any]:
        """Create a route through specific waypoints"""
        try:
            print(f"🛤️  Creating {transport_mode} route through {len(waypoints)} waypoints")
            
            # Convert waypoints to coordinate tuples
            coords = [(wp['lat'], wp['lon']) for wp in waypoints]
            
            route = self.path_agent.get_route_with_waypoints(coords)
            
            if route and 'routes' in route and route['routes']:
                distance_km = route['routes'][0]['distance'] / 1000
                duration_min = route['routes'][0]['duration'] / 60
                
                return {
                    "success": True,
                    "route": route,
                    "waypoints_used": waypoints,
                    "summary": {
                        "distance_km": round(distance_km, 2),
                        "duration_minutes": round(duration_min, 1),
                        "waypoints": len(route['routes'][0]['geometry']['coordinates']),
                        "detour_points": len(waypoints)
                    }
                }
            else:
                return {"success": False, "error": "No route found through waypoints"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_route_to_file(self, route_data: Dict[str, Any], filename: str = "route.json") -> Dict[str, Any]:
        """Save route data to a GeoJSON file"""
        try:
            print(f"💾 Saving route to {filename}")
            
            # Extract geometry from OSRM response
            if 'routes' in route_data and route_data['routes']:
                geometry = route_data['routes'][0]['geometry']
                
                # Create GeoJSON structure
                geojson = {
                    "type": "Feature",
                    "geometry": geometry,
                    "properties": {
                        "distance": route_data['routes'][0]['distance'],
                        "duration": route_data['routes'][0]['duration']
                    }
                }
                
                with open(filename, 'w') as f:
                    json.dump(geojson, f, indent=2)
                
                return {
                    "success": True,
                    "filename": filename,
                    "coordinates_count": len(geometry['coordinates'])
                }
            else:
                return {"success": False, "error": "Invalid route data"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    def analyze_route_for_specific_amenities(self, geojson_file: str, amenity_types: List[str], 
                                       sample_distance_m: int = 300, detour_radius_m: int = 200) -> Dict[str, Any]:
        """Analyze a route for specific amenity types selected by the AI"""
        try:
            print(f"🔍 Analyzing route {geojson_file} for specific amenities: {amenity_types}")
            
            # First, run the full analysis to get all amenities
            analysis = self.route_agent.analyze_route(
                geojson_file, 
                sample_distance_m, 
                detour_radius_m
            )
            
            if 'error' in analysis:
                return {"success": False, "error": analysis['error']}
            
            # Now filter the results based on the specific amenity types requested
            filtered_analysis = self._extract_specific_amenities(analysis, amenity_types)
            
            # Save the filtered analysis
            filtered_report_file = os.path.splitext(geojson_file)[0] + "_targeted_amenities.json"
            with open(filtered_report_file, "w") as f:
                json.dump(filtered_analysis, f, indent=2)
            
            return {
                "success": True,
                "analysis": filtered_analysis,
                "filtered_report_file": filtered_report_file,
                "summary": {
                    "requested_amenity_types": amenity_types,
                    "total_matching_amenities": filtered_analysis['total_matching_amenities'],
                    "route_distance_km": analysis['route_info']['route_distance_km']
                }
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _extract_specific_amenities(self, analysis: Dict[str, Any], amenity_types: List[str]) -> Dict[str, Any]:
        """Extract only the specific amenity types requested by the AI from the full analysis"""
        print("🔎 Extracting specific amenities from analysis")
        if 'route_segments' not in analysis:
            return analysis

        # Convert requested types to lowercase for matching
        target_types = [atype.lower() for atype in amenity_types]

        matching_locations = []
        total_matching_amenities = 0

        for segment in analysis['route_segments']:
            if 'detours' not in segment:
                continue
            
            matching_amenities = []
            
            for detour in segment['detours']:
                # Only process amenity detours
                if detour['type'] != 'amenity':
                    continue
                    
                amenity_data = detour['amenity']
                
                # Check if this amenity matches any of the requested types
                amenity_type_lower = amenity_data['type'].lower()
                amenity_name_lower = amenity_data['name'].lower()
                
                # Check if any target type is in the amenity type or name
                matches = False
                matched_type = None
                
                for target_type in target_types:
                    # Be very specific about matching
                    if (target_type in amenity_type_lower or 
                        target_type in amenity_name_lower):
                        matches = True
                        matched_type = target_type
                        break
                
                if matches:
                    # Skip if too far from route (>300m)
                    if amenity_data['distance_from_route_m'] > 300:
                        continue
                    
                    # Only include essential data
                    matching_amenities.append({
                        'name': amenity_data['name'],
                        'type': amenity_data['type'],
                        'distance_m': round(amenity_data['distance_from_route_m'], 1),
                        'location': {
                            'lat': amenity_data['location'][0],
                            'lon': amenity_data['location'][1]
                        },
                        'matched_type': matched_type,
                        'osm_link': amenity_data.get('osm_link', '')
                    })
            
            if matching_amenities:
                # Group by the matched type
                grouped_amenities = {}
                for amenity in matching_amenities:
                    matched_type = amenity['matched_type']
                    if matched_type not in grouped_amenities:
                        grouped_amenities[matched_type] = []
                    grouped_amenities[matched_type].append(amenity)
                
                matching_locations.append({
                    'coordinate': segment['coordinate'],
                    'amenities_by_type': grouped_amenities,
                    'total_amenities': len(matching_amenities)
                })
                
                total_matching_amenities += len(matching_amenities)
        
        return {
            'route_info': analysis['route_info'],
            'requested_amenity_types': amenity_types,
            'total_matching_amenities': total_matching_amenities,
            'matching_locations': matching_locations,
            'summary': f"Found {total_matching_amenities} amenities matching types: {', '.join(amenity_types)}"
        }
    
    def find_detour_point(self, geojson_file: str, amenity_type: str, 
                     amenity_name: str = None, max_detour_distance: int = 300) -> Dict[str, Any]:
        """Find a specific amenity point for detour routing"""
        try:
            # Analyze route for amenities with specific filter
            analysis = self.route_agent.analyze_route(geojson_file, detour_radius_m=max_detour_distance)
            
            if 'error' in analysis:
                return {"success": False, "error": analysis['error']}
            
            # Search for matching amenities
            matching_amenities = []
            
            for segment in analysis['route_segments']:
                for detour in segment['detours']:
                    if detour['type'] == 'amenity':
                        amenity = detour['amenity']
                        
                        # Check if amenity type matches
                        if amenity_type.lower() in amenity['type'].lower():
                            # If specific name requested, check that too
                            if amenity_name and amenity_name.lower() not in amenity['name'].lower():
                                continue
                            
                            matching_amenities.append({
                                'amenity': amenity,
                                'detour_distance': detour['detour_distance_m'],
                                'route_point': segment['coordinate']
                            })
            
            if not matching_amenities:
                return {"success": False, "error": f"No {amenity_type} found along route"}
            
            # Sort by detour distance and return best option
            matching_amenities.sort(key=lambda x: x['detour_distance'])
            best_match = matching_amenities[0]
            
            return {
                "success": True,
                "detour_point": {
                    "name": best_match['amenity']['name'],
                    "type": best_match['amenity']['type'],
                    "lat": best_match['amenity']['location'][0],
                    "lon": best_match['amenity']['location'][1],
                    "detour_distance_m": best_match['detour_distance']
                },
                "alternatives": matching_amenities[1:3] if len(matching_amenities) > 1 else []
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_route(self, start_lat: float, start_lon: float, end_lat: float, end_lon: float, 
                avoid_highways: bool = True, transport_mode: str = "bicycle") -> Dict[str, Any]:
        """Create a route using the path agent"""
        try:
            print(f"🚴 Creating {transport_mode} route from ({start_lat}, {start_lon}) to ({end_lat}, {end_lon})")
            
            if transport_mode == "bicycle":
                route = self.path_agent.smart_reroute(start_lat, start_lon, end_lat, end_lon, save_filename="route.json")
            else:
                # For foot travel, use basic routing (you could enhance this)
                route = self.path_agent.get_bike_friendly_route(start_lat, start_lon, end_lat, end_lon, avoid_highways, save_filename="route.json")
            
            if route and 'routes' in route and route['routes']:
                distance_km = route['routes'][0]['distance'] / 1000
                duration_min = route['routes'][0]['duration'] / 60
                
                return {
                    "success": True,
                    "route": route,
                    "summary": {
                        "distance_km": round(distance_km, 2),
                        "duration_minutes": round(duration_min, 1),
                        "waypoints": len(route['routes'][0]['geometry']['coordinates'])
                    }
                }
            else:
                return {"success": False, "error": "No route found"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_detour_route(self, start_lat: float, start_lon: float, 
                        detour_lat: float, detour_lon: float,
                        end_lat: float, end_lon: float,
                        transport_mode: str = "bicycle") -> Dict[str, Any]:
        """Create a route with a detour by combining two separate routes"""
        try:
            print(f"🛤️  Creating detour route: Start -> Detour -> End")
            
            # Create two separate routes using path agent with specific filenames
            print("📍 Creating route 1: Start -> Detour")
            if transport_mode == "bicycle":
                route1_osrm = self.path_agent.smart_reroute(start_lat, start_lon, detour_lat, detour_lon, save_filename="route1_temp.json")
            else:
                route1_osrm = self.path_agent.get_bike_friendly_route(start_lat, start_lon, detour_lat, detour_lon, save_filename="route1_temp.json")
            
            print("📍 Creating route 2: Detour -> End") 
            if transport_mode == "bicycle":
                route2_osrm = self.path_agent.smart_reroute(detour_lat, detour_lon, end_lat, end_lon, save_filename="route2_temp.json")
            else:
                route2_osrm = self.path_agent.get_bike_friendly_route(detour_lat, detour_lon, end_lat, end_lon, save_filename="route2_temp.json")
            
            if not route1_osrm or 'routes' not in route1_osrm or not route1_osrm['routes']:
                return {"success": False, "error": "Failed to create route to detour point"}
            
            if not route2_osrm or 'routes' not in route2_osrm or not route2_osrm['routes']:
                return {"success": False, "error": "Failed to create route from detour point"}
            
            # Convert both OSRM responses to GeoJSON using utils
            from utils import osrm_route_to_geojson
            
            route1_geojson = osrm_route_to_geojson(route1_osrm)
            route2_geojson = osrm_route_to_geojson(route2_osrm)
            
            # Extract coordinates from both GeoJSON routes
            coords1 = route1_geojson['geometry']['coordinates']
            coords2 = route2_geojson['geometry']['coordinates']
            
            # Combine coordinates (remove first coordinate of route2 to avoid duplication)
            combined_coords = coords1 + coords2[1:]
            
            # Calculate combined properties
            total_distance = route1_geojson['properties']['distance_km'] + route2_geojson['properties']['distance_km']
            total_duration = route1_geojson['properties']['duration_minutes'] + route2_geojson['properties']['duration_minutes']
            
            # Create combined GeoJSON in the same format as route.json
            combined_geojson = {
                "type": "Feature",
                "properties": {
                    "distance_km": round(total_distance, 2),
                    "duration_minutes": round(total_duration, 1),
                    "waypoints": {
                        "start": {
                            "location": [start_lon, start_lat],
                            "name": "Start",
                            "distance_to_road": route1_osrm['waypoints'][0].get('distance', 0) if 'waypoints' in route1_osrm else 0
                        },
                        "detour": {
                            "location": [detour_lon, detour_lat],
                            "name": "Detour",
                            "distance_to_road": 0
                        },
                        "end": {
                            "location": [end_lon, end_lat],
                            "name": "End",
                            "distance_to_road": route2_osrm['waypoints'][-1].get('distance', 0) if 'waypoints' in route2_osrm else 0
                        }
                    }
                },
                "geometry": {
                    "coordinates": combined_coords,
                    "type": "LineString"
                }
            }
            
            # Save the combined route to route.json
            with open("route.json", 'w') as f:
                json.dump(combined_geojson, f, indent=2)
            print("💾 Combined detour route saved to route.json")
            
            # Clean up temporary files
            try:
                import os
                os.remove("route1_temp.json")
                os.remove("route2_temp.json")
            except:
                pass  # Don't worry if temp files don't exist
            
            return {
                "success": True,
                "route": {"routes": [{"geometry": combined_geojson["geometry"], 
                                "distance": total_distance * 1000,  # Convert back to meters for consistency
                                "duration": total_duration * 60}]},  # Convert back to seconds
            "combined_geojson": combined_geojson,
            "detour_info": {
                "detour_point": {"lat": detour_lat, "lon": detour_lon},
                "is_detour_route": True,
                "route1_distance_km": route1_geojson['properties']['distance_km'],
                "route2_distance_km": route2_geojson['properties']['distance_km']
            },
            "summary": {
                "distance_km": round(total_distance, 2),
                "duration_minutes": round(total_duration, 1),
                "waypoints": len(combined_coords),
                "segments": 2
            }
            }
        
        except Exception as e:
            return {"success": False, "error": str(e)}

    def handle_function_call(self, function_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle function calls from OpenAI"""
        
        if function_name == "create_route":
            return self.create_route(**arguments)
        elif function_name == "analyze_route_for_amenities":
            return self.analyze_route_for_amenities(**arguments)
        elif function_name == "analyze_route_for_specific_amenities":
            return self.analyze_route_for_specific_amenities(**arguments)
        elif function_name == "create_route_with_waypoints":
            return self.create_route_with_waypoints(**arguments)
        elif function_name == "save_route_to_file":
            return self.save_route_to_file(**arguments)
        elif function_name == "find_detour_point":
            return self.find_detour_point(**arguments)
        elif function_name == "create_detour_route":
            return self.create_detour_route(**arguments)
        else:
            return {"success": False, "error": f"Unknown function: {function_name}"}

    def chat(self, user_message: str, conversation_history: List[Dict[str, str]] = None) -> str:
        """Main chat interface for the orchestrator"""
        
        if conversation_history is None:
            conversation_history = []
        
        # Add user message to history
        conversation_history.append({"role": "user", "content": user_message})
        
        # Create OpenAI client directly
        from utils import create_openai_client
        client = create_openai_client(self.openai_api_key)
        
        # Prepare messages for OpenAI
        messages = [{"role": "system", "content": self.system_prompt}] + conversation_history
        
        try:
            max_tool_rounds = 5  # Prevent infinite loops
            current_round = 0
            
            while current_round < max_tool_rounds:
                # Call OpenAI with tools support
                response = client.chat.completions.create(
                    model="gpt-4",
                    messages=messages,
                    tools=self.tools,
                    tool_choice="auto",
                    temperature=0.7
                )
                
                # Check if the response contains function calls
                if response.choices[0].message.tool_calls:
                    current_round += 1
                    print(f"\n🔄 Tool calling round {current_round}")
                    
                    # Handle function calls
                    tool_results = []
                    
                    for tool_call in response.choices[0].message.tool_calls:
                        function_name = tool_call.function.name
                        arguments = json.loads(tool_call.function.arguments)
                        
                        print(f"🔧 Calling function: {function_name}")
                        print(f"📝 Arguments: {arguments}")
                        
                        result = self.handle_function_call(function_name, arguments)
                        tool_results.append({
                            "tool_call_id": tool_call.id,
                            "result": result
                        })
                    
                    # Add assistant's function call to messages
                    messages.append({
                        "role": "assistant", 
                        "content": response.choices[0].message.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function", 
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments
                            }
                        } for tc in response.choices[0].message.tool_calls
                        ]
                    })
                    
                    # Add tool results to messages
                    for tool_result in tool_results:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_result["tool_call_id"],
                            "content": json.dumps(tool_result["result"])
                        })
                    
                    # Continue the loop to allow another round of tool calling
                    
                else:
                    # No more function calls, this is the final response
                    assistant_reply = response.choices[0].message.content
                    break
            
            # If we hit the max rounds limit
            if current_round >= max_tool_rounds:
                print(f"\n⚠️  Reached maximum tool calling rounds ({max_tool_rounds})")
                assistant_reply = response.choices[0].message.content or "I've completed the available actions but reached the maximum number of tool calls."
            
            # Update conversation history with all the messages from this interaction
            # Skip the system prompt and original user message since they're already in history
            new_messages = messages[len([{"role": "system", "content": self.system_prompt}] + conversation_history):]
            conversation_history.extend(new_messages)
            
            # Add assistant's final response to history
            conversation_history.append({"role": "assistant", "content": assistant_reply})
            
            return assistant_reply
            
        except Exception as e:
            error_msg = f"❌ Error in orchestrator: {str(e)}"
            print(error_msg)
            return error_msg


def main():
    """Example usage of the orchestrator"""
    
    # Get API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ Please set OPENAI_API_KEY environment variable")
        return
    
    # Initialize orchestrator
    orchestrator = RouteOrchestrator(api_key)
    
    print("🚴 Route Planning Assistant Ready!")
    print("Ask me to plan a route, find amenities, or create detours.")
    print("Type 'quit' to exit.\n")
    
    conversation_history = []
    
    while True:
        user_input = input("\n💬 You: ").strip()
        
        if user_input.lower() in ['quit', 'exit', 'bye']:
            print("👋 Goodbye!")
            break
        
        if not user_input:
            continue
        
        print("\n🤖 Assistant: ", end="")
        response = orchestrator.chat(user_input, conversation_history)
        print(response)


if __name__ == "__main__":
    main()