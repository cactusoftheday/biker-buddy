import json
import overpy
import math
from typing import List, Dict, Any, Tuple, Optional
from utils import chat_with_openai
import dotenv


class RouteAnalysisAgent:
    def __init__(self, openai_api_key: str):
        """
        Initialize the route analysis agent.
        
        Args:
            openai_api_key: Your OpenAI API key
        """
        self.openai_api_key = openai_api_key
        self.overpass_api = overpy.Overpass()
        
        self.system_prompt = """
        You are a helpful assistant that analyzes Points of Interest (POIs) and simple detour opportunities along bicycle and walking routes.
        Your task is to identify useful amenities and describe how to reach them from the main route, focusing on:
        
        1. Essential amenities (food, water, restrooms, bike shops)
        2. Safety considerations for cyclists/pedestrians
        3. Simple navigation instructions to reach POIs
        4. Quick detour assessments (worth the detour or not)
        5. Estimated detour distance and difficulty
        
        When suggesting detours, consider:
        - How far off the main route the amenity is
        - Whether there's a clear path to reach it
        - Value of the amenity for cyclists/pedestrians
        - Safety of the detour route
        
        Provide practical, concise descriptions that would be useful for someone traveling this route.
        Focus on cyclist and pedestrian perspectives.
        """
    
    def load_geojson_route(self, geojson_file: str) -> List[Tuple[float, float]]:
        """
        Load coordinates from a GeoJSON file.
        
        Args:
            geojson_file: Path to the GeoJSON file
            
        Returns:
            List of (latitude, longitude) coordinate pairs
        """
        try:
            with open(geojson_file, 'r') as f:
                geojson = json.load(f)
            
            if geojson['type'] == 'Feature':
                coordinates = geojson['geometry']['coordinates']
            elif geojson['type'] == 'FeatureCollection':
                # Take the first feature
                coordinates = geojson['features'][0]['geometry']['coordinates']
            else:
                raise ValueError("Invalid GeoJSON format")
            
            # Convert [lon, lat] to [lat, lon] for easier processing
            return [(coord[1], coord[0]) for coord in coordinates]
            
        except Exception as e:
            print(f"❌ Error loading GeoJSON: {e}")
            return []
    
    def sample_route_coordinates(self, coordinates: List[Tuple[float, float]], 
                                sample_distance_m: float = 200) -> List[Tuple[float, float]]:
        """
        Sample coordinates along the route at specified intervals.
        """
        if not coordinates:
            return []
        
        sampled = [coordinates[0]]  # Always include start
        
        for i in range(1, len(coordinates)):
            last_sampled = sampled[-1]
            current = coordinates[i]
            
            distance = self.haversine_distance(last_sampled, current) * 1000  # Convert to meters
            
            if distance >= sample_distance_m:
                sampled.append(current)
        
        # Always include end if it's not already sampled
        if coordinates[-1] not in sampled:
            sampled.append(coordinates[-1])
        
        return sampled
    
    def haversine_distance(self, coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
        """
        Calculate the great circle distance between two points in kilometers.
        """
        lat1, lon1 = coord1
        lat2, lon2 = coord2
        
        # Convert to radians
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        r = 6371  # Radius of earth in kilometers
        
        return c * r

    def find_detour_opportunities(self, lat: float, lon: float, 
                        search_radius_m: float = 200) -> List[Dict[str, Any]]:
        """
        Find amenities and nearby ways near a coordinate.
        
        Args:
            lat: Latitude
            lon: Longitude
            search_radius_m: Search radius in meters
            
        Returns:
            List of detour opportunities (amenities + ways)
        """
        # Convert radius to degrees
        radius_deg = search_radius_m / 111000
        
        south = lat - radius_deg
        north = lat + radius_deg
        west = lon - radius_deg
        east = lon + radius_deg
        
        # Query for amenities - NODES AND WAYS with complete geometry
        amenity_query = f"""
        [out:json][timeout:25];
        (
        node["amenity"~"^(restaurant|cafe|fast_food|pub|bar|fuel|bank|atm|pharmacy|hospital|toilets|drinking_water|bicycle_parking|bicycle_rental|bicycle_repair_station|water_point|fountain|bench|shelter|waste_basket|recycling)$"]({south},{west},{north},{east});
        node["shop"~"^(convenience|supermarket|bicycle|sports|outdoor|hardware|general|department_store|mall|bakery|butcher|greengrocer|alcohol|beverage)$"]({south},{west},{north},{east});
        node["tourism"~"^(information|viewpoint|attraction|museum|gallery|artwork|picnic_site)$"]({south},{west},{north},{east});
        node["leisure"~"^(park|playground|fitness_station|sports_centre|swimming_pool|golf_course|nature_reserve|garden|common|recreation_ground|pitch)$"]({south},{west},{north},{east});
        node["natural"~"^(peak|viewpoint|spring|waterfall|beach|cliff|cave_entrance)$"]({south},{west},{north},{east});
        node["historic"~"^(monument|memorial|castle|ruins|archaeological_site|wayside_cross|wayside_shrine)$"]({south},{west},{north},{east});
        way["tourism"~"^(information|viewpoint|attraction|museum|gallery|artwork|picnic_site)$"]({south},{west},{north},{east});
        way["leisure"~"^(park|playground|fitness_station|sports_centre|swimming_pool|golf_course|nature_reserve|garden|common|recreation_ground|pitch)$"]({south},{west},{north},{east});
        way["natural"~"^(peak|viewpoint|spring|waterfall|beach|cliff|cave_entrance)$"]({south},{west},{north},{east});
        way["historic"~"^(monument|memorial|castle|ruins|archaeological_site|wayside_cross|wayside_shrine)$"]({south},{west},{north},{east});
        );
        out geom;
        >;
        out skel qt;
        """
        
        # Query for detour ways
        detour_query = f"""
        [out:json][timeout:25];
        (
            way["highway"="cycleway"]({south},{west},{north},{east});
            way["highway"="path"]["bicycle"~"^(yes|designated)$"]({south},{west},{north},{east});
            way["highway"="footway"]["bicycle"="yes"]({south},{west},{north},{east});
            way["highway"="pedestrian"]({south},{west},{north},{east});
            way["highway"="track"]({south},{west},{north},{east});
            way["highway"="service"]({south},{west},{north},{east});
            way["cycleway"]({south},{west},{north},{east});
            way["bicycle"="designated"]({south},{west},{north},{east});

            way["highway"="residential"]["traffic_calming"]({south},{west},{north},{east});
            way["highway"="living_street"]({south},{west},{north},{east});
            way["maxspeed"~"^(20|30)$"]({south},{west},{north},{east});

            way["highway"~"^(footway|path|residential|tertiary|secondary|unclassified)$"]({south},{west},{north},{east});
        );
        out geom;
        >;
        out;
        """
        
        try:
            print(f"🔍 Querying OSM for area: {south:.5f},{west:.5f},{north:.5f},{east:.5f}")
            
            # Execute amenity query
            print("🏪 Querying amenities...")
            amenity_result = self.overpass_api.query(amenity_query)
            print(f"✅ Found {len(amenity_result.nodes)} amenity nodes")
            
            # Execute detour query
            print("🛣️  Querying detour ways...")
            detour_result = self.overpass_api.query(detour_query)
            print(f"✅ Found {len(detour_result.ways)} detour ways")
            
            # Debug: Check if ways have proper geometry
            ways_with_geom = sum(1 for way in detour_result.ways if hasattr(way, 'nodes') and way.nodes)
            ways_without_geom = len(detour_result.ways) - ways_with_geom
            print(f"📊 Detour ways with geometry: {ways_with_geom}, without geometry: {ways_without_geom}")
            
            # Process amenity nodes
            amenities = []
            for node in amenity_result.nodes:
                amenity_info = self.extract_amenity_info(node, lat, lon)
                if amenity_info:
                    amenities.append(amenity_info)

            # Process amenity ways with error handling
            amenity_ways_processed = 0
            amenity_ways_failed = 0

            for way in amenity_result.ways:
                try:
                    amenity_info = self.extract_amenity_way_info(way, lat, lon)
                    if amenity_info:
                        amenities.append(amenity_info)
                        amenity_ways_processed += 1
                    else:
                        amenity_ways_failed += 1
                except Exception as e:
                    amenity_ways_failed += 1
                    print(f"⚠️  Failed to process amenity way {getattr(way, 'id', 'unknown')}: {e}")

            print(f"📊 Processed: {len(amenities)} total amenities")
            print(f"📊 Amenity ways: {amenity_ways_processed} successful, {amenity_ways_failed} failed")
            
            # Process detour ways - extract just ID and middle node
            all_ways = []
            regular_ways_processed = 0
            regular_ways_failed = 0
            
            for way in detour_result.ways:
                way_info = self.extract_simple_way_info(way)
                if way_info:
                    all_ways.append(way_info)
                    regular_ways_processed += 1
                else:
                    regular_ways_failed += 1
                    print(f"⚠️  Failed to extract info for way {way.id} ({way.tags.get('highway', 'unknown')})")
            
            print(f"📊 Processed: {len(amenities)} amenities")
            print(f"📊 Regular ways: {regular_ways_processed} successful, {regular_ways_failed} failed")
            
            # Create detour opportunities
            detour_opportunities = []
            
            # Add amenity-based detours
            for amenity in amenities:
                detour = self.create_amenity_detour(amenity, lat, lon)
                detour_opportunities.append(detour)
            
            # Add ways as potential detours
            for way in all_ways:
                way_detour = self.create_simple_way_detour(way, lat, lon)
                detour_opportunities.append(way_detour)
            
            print(f"📊 Created {len(detour_opportunities)} detour opportunities")
            
            return detour_opportunities
            
        except Exception as e:
            print(f"⚠️  Error finding detour opportunities near ({lat:.5f}, {lon:.5f}): {e}")
            return []
    
    def extract_simple_way_info(self, way) -> Optional[Dict[str, Any]]:
        """Extract simple information about a way (just ID and middle node for detour routing)."""
        try:
            # Check if way has node references
            if not hasattr(way, 'nodes') or not way.nodes:
                return None
            
            # Find nodes with coordinates
            valid_nodes = []
            for node_ref in way.nodes:
                lat_val = None
                lon_val = None
                
                if hasattr(node_ref, 'lat') and node_ref.lat is not None:
                    lat_val = float(node_ref.lat)
                if hasattr(node_ref, 'lon') and node_ref.lon is not None:
                    lon_val = float(node_ref.lon)
                
                if lat_val is not None and lon_val is not None:
                    valid_nodes.append((lat_val, lon_val))
    
            if len(valid_nodes) < 2:
                return None
            
            # Find middle node for routing purposes
            middle_index = len(valid_nodes) // 2
            middle_lat, middle_lon = valid_nodes[middle_index]
            
            # Extract way tags
            tags = way.tags
            highway = tags.get('highway', 'unknown')
            maxspeed = tags.get('maxspeed', '')
            surface = tags.get('surface', '')
            name = tags.get('name', '')
            bicycle = tags.get('bicycle', '')
            foot = tags.get('foot', '')
            
            return {
                'id': way.id,
                'highway': highway,
                'name': name,
                'maxspeed': maxspeed,
                'surface': surface,
                'bicycle': bicycle,
                'foot': foot,
                'middle_node': {
                    'lat': middle_lat,
                    'lon': middle_lon
                },
                'node_count': len(valid_nodes),
                'osm_link': f"https://openstreetmap.org/way/{way.id}"
            }
        
        except Exception as e:
            print(f"⚠️  Error extracting simple way info for way {getattr(way, 'id', 'unknown')}: {e}")
            return None
    
    # ...existing code...
    def extract_amenity_info(self, node, route_lat: float, route_lon: float) -> Optional[Dict[str, Any]]:
        """Extract information about an amenity node."""
        try:
            if not (hasattr(node, 'lat') and hasattr(node, 'lon') and 
                   node.lat is not None and node.lon is not None):
                return None
                
            amenity_lat = float(node.lat)
            amenity_lon = float(node.lon)
            
            # Calculate distance from route point
            distance = self.haversine_distance((route_lat, route_lon), (amenity_lat, amenity_lon)) * 1000
            
            tags = node.tags
            
            # Determine amenity type
            amenity_type = "unknown"
            category = "other"
            
            for key, value in tags.items():
                if key in ['amenity', 'shop', 'tourism']:
                    amenity_type = f"{key}={value}"
                    category = key
                    break
            
            name = tags.get('name', f"Unnamed {amenity_type}")
            brand = tags.get('brand', '')
            opening_hours = tags.get('opening_hours', '')
            
            return {
                'id': node.id,
                'name': name,
                'type': amenity_type,
                'category': category,
                'brand': brand,
                'opening_hours': opening_hours,
                'location': (amenity_lat, amenity_lon),
                'distance_from_route_m': round(distance, 1),
                'osm_link': f"https://openstreetmap.org/node/{node.id}"
            }
        
        except Exception as e:
            print(f"⚠️  Error extracting amenity info: {e}")
            return None
    
    def extract_amenity_way_info(self, way, route_lat: float, route_lon: float) -> Optional[Dict[str, Any]]:
        """Extract information about an amenity way (like parks, tourist attractions)."""
        try:
            # Check if way has node references
            if not hasattr(way, 'nodes') or not way.nodes:
                print(f"⚠️  Way {way.id} has no node references")
                return None
            
            # Find nodes with coordinates from the resolved nodes
            valid_nodes = []
            for node_ref in way.nodes:
                # The node_ref should have lat/lon if the query resolved properly
                lat_val = None
                lon_val = None
                
                if hasattr(node_ref, 'lat') and node_ref.lat is not None:
                    lat_val = float(node_ref.lat)
                if hasattr(node_ref, 'lon') and node_ref.lon is not None:
                    lon_val = float(node_ref.lon)
                
                if lat_val is not None and lon_val is not None:
                    valid_nodes.append((lat_val, lon_val))

            if len(valid_nodes) < 2:
                print(f"⚠️  Way {way.id} has insufficient valid nodes: {len(valid_nodes)}")
                return None
            
            # Calculate center point of the way for distance calculation
            center_lat = sum(coord[0] for coord in valid_nodes) / len(valid_nodes)
            center_lon = sum(coord[1] for coord in valid_nodes) / len(valid_nodes)
            
            # Calculate distance from route point to center of way
            distance = self.haversine_distance((route_lat, route_lon), (center_lat, center_lon)) * 1000
            
            tags = way.tags
            
            # Determine amenity type and category
            amenity_type = "unknown"
            category = "other"
            
            # Check different tag categories for ways
            tag_categories = {
                'tourism': 'tourism',
                'leisure': 'leisure',
                'natural': 'natural',
                'historic': 'historic',
                'amenity': 'amenity',
                'shop': 'shop'
            }
            
            for key, cat in tag_categories.items():
                if key in tags:
                    amenity_type = f"{key}={tags[key]}"
                    category = cat
                    break
            
            name = tags.get('name', f"Unnamed {amenity_type}")
            brand = tags.get('brand', '')
            opening_hours = tags.get('opening_hours', '')
            website = tags.get('website', '')
            phone = tags.get('phone', '')
            
            # Add category-specific useful info for ways
            additional_info = {}
            if category == 'leisure':
                additional_info['park_type'] = tags.get('park:type', '')
                additional_info['access'] = tags.get('access', 'public')
                additional_info['sport'] = tags.get('sport', '')
            elif category == 'natural':
                additional_info['elevation'] = tags.get('ele', '')
                additional_info['natural_type'] = tags.get('natural', '')
            elif category == 'tourism':
                additional_info['tourism_type'] = tags.get('tourism', '')
                additional_info['wheelchair'] = tags.get('wheelchair', '')
            elif category == 'historic':
                additional_info['historic_type'] = tags.get('historic', '')
                additional_info['heritage'] = tags.get('heritage', '')
            
            return {
                'id': way.id,
                'name': name,
                'type': amenity_type,
                'category': category,
                'brand': brand,
                'opening_hours': opening_hours,
                'website': website,
                'phone': phone,
                'additional_info': additional_info,
                'location': (center_lat, center_lon),
                'distance_from_route_m': round(distance, 1),
                'geometry_type': 'way',
                'node_count': len(valid_nodes),
                'osm_link': f"https://openstreetmap.org/way/{way.id}"
            }
    
        except Exception as e:
            print(f"⚠️  Error extracting amenity way info for way {getattr(way, 'id', 'unknown')}: {e}")
            return None

    def create_amenity_detour(self, amenity: Dict[str, Any], 
                         main_route_lat: float, main_route_lon: float) -> Dict[str, Any]:
        """Create a detour opportunity for an amenity."""
        return {
            'type': 'amenity',
            'amenity': amenity,
            'detour_distance_m': amenity['distance_from_route_m'],
            'description': f"{amenity['name']} ({amenity['type']}) - {amenity['distance_from_route_m']:.0f}m from route"
        }

    def create_simple_way_detour(self, way: Dict[str, Any], 
                     main_route_lat: float, main_route_lon: float) -> Dict[str, Any]:
        """Create a simple detour opportunity for a way with just ID and middle node."""
        
        # Calculate distance from main route to middle node
        mid_lat = way['middle_node']['lat']
        mid_lon = way['middle_node']['lon']
        distance = self.haversine_distance((main_route_lat, main_route_lon), (mid_lat, mid_lon)) * 1000
        
        return {
            'type': 'way',
            'way': way,
            'detour_distance_m': distance,
            'description': f"Way {way['id']} - {distance:.0f}m from route"
        }
    
    def analyze_route(self, geojson_file: str, sample_distance_m: float = 300, 
                 detour_radius_m: float = 200) -> Dict[str, Any]:
        """
        Analyze a complete route for detour opportunities.
        """
        print(f"🗺️  Analyzing route from {geojson_file}")
        
        # Load route coordinates
        coordinates = self.load_geojson_route(geojson_file)
        if not coordinates:
            return {"error": "Could not load route coordinates"}
        
        print(f"📍 Route has {len(coordinates)} coordinate points")
        
        # Sample coordinates
        sampled_coords = self.sample_route_coordinates(coordinates, sample_distance_m)
        print(f"🎯 Analyzing {len(sampled_coords)} sample points")
        
        # Find detour opportunities at each sample point
        all_detours = []
        route_segments = []
        
        for i, (lat, lon) in enumerate(sampled_coords):
            print(f"🔍 Searching detours near point {i+1}/{len(sampled_coords)}...")
            
            detours = self.find_detour_opportunities(lat, lon, detour_radius_m)
            print(f"    Found {len(detours)} detours at this point")
            
            segment_data = {
                'segment_id': i + 1,
                'coordinate': (lat, lon),
                'detour_count': len(detours),
                'detours': detours
            }
            route_segments.append(segment_data)
            all_detours.extend(detours)

        print(f"📊 Total detours found before deduplication: {len(all_detours)}")

        # Calculate actual route distance
        route_distance_km = 0
        for i in range(len(coordinates) - 1):
            route_distance_km += self.haversine_distance(coordinates[i], coordinates[i + 1])

        # Remove duplicate detours by ID
        unique_detours = {}
        for detour in all_detours:
            if detour['type'] == 'amenity':
                key = f"amenity_{detour['amenity']['id']}"
            elif detour['type'] == 'way':
                key = f"way_{detour['way']['id']}"
            else:
                continue
    
            if key not in unique_detours:
                unique_detours[key] = detour

        unique_detours = list(unique_detours.values())
        print(f"📊 After deduplication: {len(unique_detours)} unique detours")

        # Categorize detours
        amenity_detours = [d for d in unique_detours if d['type'] == 'amenity']
        way_detours = [d for d in unique_detours if d['type'] == 'way']

        print(f"📊 Final counts: {len(amenity_detours)} amenities, {len(way_detours)} ways")

        return {
            'route_file': geojson_file,
            'analysis_date': None,  # Will be filled when saved
            'route_info': {
                'total_coordinates': len(coordinates),
                'sampled_points': len(sampled_coords),
                'route_distance_km': round(route_distance_km, 2),
                'start_coordinate': coordinates[0],
                'end_coordinate': coordinates[-1]
            },
            'detour_summary': {
                'total_detours': len(unique_detours),
                'amenity_detours': len(amenity_detours),
                'way_detours': len(way_detours)
            },
            'route_segments': route_segments,
            'all_detours': {
                'amenities': amenity_detours,
                'ways': way_detours
            }
        }

    def save_analysis_report(self, analysis: Dict[str, Any], output_file: str = "detour_opportunities.json"):
        """Save the analysis to a JSON file with detours grouped by sampling points."""

        # Add timestamp
        from datetime import datetime
        analysis['analysis_date'] = datetime.now().isoformat()

        print(f"💾 Saving analysis with {analysis['detour_summary']['amenity_detours']} amenities and {analysis['detour_summary']['way_detours']} ways")

        # Create a clean structure for the JSON output
        clean_output = {
            'route_info': analysis['route_info'],
            'analysis_date': analysis['analysis_date'],
            'detour_summary': analysis['detour_summary'],
            'sampling_points': []
        }

        # Process each route segment/sampling point
        for segment in analysis['route_segments']:
            segment_info = {
                'point_id': segment['segment_id'],
                'coordinate': {
                    'lat': segment['coordinate'][0],
                    'lon': segment['coordinate'][1]
                },
                'detour_count': segment['detour_count'],
                'detours': {
                    'amenities': [],
                    'ways': []
                }
            }

            # Group detours by type for this sampling point
            for detour in segment['detours']:
                if detour['type'] == 'amenity':
                    amenity = detour['amenity']
                    amenity_info = {
                        'id': amenity['id'],
                        'name': amenity['name'],
                        'type': amenity['type'],
                        'category': amenity['category'],
                        'brand': amenity['brand'],
                        'opening_hours': amenity['opening_hours'],
                        'distance_from_route_m': detour['detour_distance_m'],
                        'location': {
                            'lat': amenity['location'][0],
                            'lon': amenity['location'][1]
                        },
                        'osm_link': amenity['osm_link']
                    }
                    segment_info['detours']['amenities'].append(amenity_info)
                
                elif detour['type'] == 'way':
                    way = detour['way']
                    way_info = {
                        'id': way['id'],
                        'highway': way.get('highway'),
                        'maxspeed': way.get('maxspeed'),
                        'surface': way.get('surface'),
                        'distance_from_route_m': detour['detour_distance_m'],
                        'middle_node': way['middle_node']
                    }
                    segment_info['detours']['ways'].append(way_info)

        clean_output['sampling_points'].append(segment_info)

        with open(output_file, 'w') as f:
            json.dump(clean_output, f, indent=2, default=str)

        print(f"📋 Analysis saved to {output_file}")
        print(f"🎯 Saved {len(clean_output['sampling_points'])} sampling points")
        
        # Count total unique detours across all points
        total_amenities = sum(len(point['detours']['amenities']) for point in clean_output['sampling_points'])
        total_ways = sum(len(point['detours']['ways']) for point in clean_output['sampling_points'])
        
        print(f"🏪 Total amenity instances: {total_amenities}")
        print(f"🛣️  Total way instances: {total_ways}")
        print(f"📍 Note: Same amenities/ways may appear at multiple sampling points")

        return output_file


def analyze_my_route():
    """Example usage of the RouteAnalysisAgent"""
    
    # Initialize the agent
    api_key = "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"
    agent = RouteAnalysisAgent(api_key)
    
    # Analyze the route
    analysis = agent.analyze_route(
        geojson_file="/home/isaac/biker/route.json",
        sample_distance_m=250,    # Sample every 250 meters
        detour_radius_m=250       # Look 250m around each point for detours
    )
    
    # Print summary
    if 'error' not in analysis:
        print(f"\n🎯 DETOUR OPPORTUNITIES ANALYSIS")
        print("=" * 50)
        print(f"📏 Route distance: {analysis['route_info']['route_distance_km']} km")
        print(f"🏪 Amenities found: {analysis['detour_summary']['amenity_detours']}")
        print(f"🛣️  Ways found: {analysis['detour_summary']['way_detours']}")
        
        # Save detailed report
        agent.save_analysis_report(analysis, "detour_opportunities.json")
    
    return analysis


if __name__ == "__main__":
    analyze_my_route()