import openai
import json
from typing import List, Dict, Optional, Any


def create_openai_client(api_key: str):
    """
    Initializes and returns the OpenAI API client with the given API key.
    """
    return openai.OpenAI(api_key=api_key)


def format_messages(
    system_prompt: str,
    user_prompt: str,
    additional_messages: Optional[List[Dict[str, str]]] = None
) -> List[Dict[str, str]]:
    """
    Formats the messages for a chat completion request.
    """
    messages = [{"role": "system", "content": system_prompt}]
    if additional_messages:
        messages.extend(additional_messages)
    messages.append({"role": "user", "content": user_prompt})
    return messages


def call_chat_completion(
    messages: List[Dict[str, str]],
    model: str = "gpt-4",
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    client: Optional[Any] = None,
    **kwargs
) -> str:
    """
    Calls the OpenAI Chat Completions API and returns the assistant's response.
    """
    if client is None:
        raise ValueError("OpenAI client must be provided")
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs
    )
    response = response.model_dump()  # Convert pydantic object to dict
    return response["choices"][0]["message"]["content"].strip()
def chat_with_openai(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    additional_messages: Optional[List[Dict[str, str]]] = None,
    model: str = "gpt-4",
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    **kwargs
) -> str:
    """
    High-level utility to initialize the client, format messages, and get a response.
    """
    client = create_openai_client(api_key)
    messages = format_messages(system_prompt, user_prompt, additional_messages)
    return call_chat_completion(messages, model, temperature, max_tokens, client=client, **kwargs)


def osrm_route_to_geojson(osrm_response: Dict[str, Any], include_properties: bool = True) -> Dict[str, Any]:
    """
    Convert OSRM route response to GeoJSON format.
    
    Args:
        osrm_response: The response from OSRM routing API
        include_properties: Whether to include route metadata in properties
    
    Returns:
        GeoJSON Feature containing the route as a LineString
    """
    if not osrm_response or 'routes' not in osrm_response or not osrm_response['routes']:
        raise ValueError("Invalid or empty OSRM response")
    
    route = osrm_response['routes'][0]  # Take the first (best) route
    
    # Extract the geometry (coordinates)
    if 'geometry' not in route:
        raise ValueError("No geometry found in route")
    
    geometry = route['geometry']
    
    # Build properties with route metadata
    properties = {}
    if include_properties:
        properties = {
            'distance_km': round(route.get('distance', 0) / 1000, 2),
            'duration_minutes': round(route.get('duration', 0) / 60, 1),
            'weight': route.get('weight', 0),
            'weight_name': route.get('weight_name', 'unknown')
        }
        
        # Add waypoint information if available
        if 'waypoints' in osrm_response:
            waypoints = osrm_response['waypoints']
            properties['waypoints'] = {
                'start': {
                    'location': waypoints[0]['location'],
                    'name': waypoints[0].get('name', 'Start'),
                    'distance_to_road': round(waypoints[0].get('distance', 0), 2)
                },
                'end': {
                    'location': waypoints[-1]['location'],
                    'name': waypoints[-1].get('name', 'End'),
                    'distance_to_road': round(waypoints[-1].get('distance', 0), 2)
                }
            }
    
    # Create GeoJSON Feature
    geojson = {
        "type": "Feature",
        "properties": properties,
        "geometry": geometry
    }
    
    return geojson


def save_route_geojson(osrm_response: Dict[str, Any], filename: str = "route.geojson") -> str:
    """
    Convert OSRM route to GeoJSON and save to file.
    
    Args:
        osrm_response: The response from OSRM routing API
        filename: Output filename for the GeoJSON file
    
    Returns:
        The filename of the saved file
    """
    geojson = osrm_route_to_geojson(osrm_response)
    
    with open(filename, 'w') as f:
        json.dump(geojson, f, indent=2)
    
    print(f"✅ Route saved to {filename}")
    print(f"📏 Distance: {geojson['properties']['distance_km']} km")
    print(f"⏱️  Duration: {geojson['properties']['duration_minutes']} minutes")
    print(f"📍 Coordinates: {len(geojson['geometry']['coordinates'])} points")
    
    return filename


def create_route_collection_geojson(routes: List[Dict[str, Any]], route_names: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Create a GeoJSON FeatureCollection from multiple OSRM routes.
    
    Args:
        routes: List of OSRM route responses
        route_names: Optional names for each route
    
    Returns:
        GeoJSON FeatureCollection with multiple route features
    """
    features = []
    
    for i, route_response in enumerate(routes):
        try:
            geojson_feature = osrm_route_to_geojson(route_response)
            
            # Add route identifier
            route_name = route_names[i] if route_names and i < len(route_names) else f"Route {i+1}"
            geojson_feature['properties']['route_name'] = route_name
            geojson_feature['properties']['route_id'] = i
            
            features.append(geojson_feature)
            
        except Exception as e:
            print(f"⚠️  Warning: Could not convert route {i+1}: {e}")
            continue
    
    return {
        "type": "FeatureCollection",
        "features": features
    }


# Example usage function
def example_route_conversion():
    """Example of how to use the route conversion functions"""
    
    # Your OSRM response
    osrm_response = {
        'code': 'Ok', 
        'routes': [{
            'legs': [{'steps': [], 'weight': 252.1, 'summary': '', 'duration': 213.6, 'distance': 1594.6}], 
            'weight_name': 'routability', 
            'geometry': {
                'coordinates': [[-114.224626, 51.04432], [-114.224597, 51.044317], [-114.224534, 51.044331]], 
                'type': 'LineString'
            }, 
            'weight': 252.1, 
            'duration': 213.6, 
            'distance': 1594.6
        }], 
        'waypoints': [
            {'location': [-114.224626, 51.04432], 'name': 'Start', 'distance': 6.626744218}, 
            {'location': [-114.209498, 51.040361], 'name': 'End', 'distance': 0.492262465}
        ]
    }
    
    # Convert to GeoJSON
    print("🗺️  Converting OSRM route to GeoJSON...")
    geojson = osrm_route_to_geojson(osrm_response)
    
    # Print the result
    print("📋 GeoJSON created:")
    print(json.dumps(geojson, indent=2)[:500] + "...")
    
    # Save to file
    filename = save_route_geojson(osrm_response, "example_route.geojson")
    
    return geojson


if __name__ == "__main__":
    example_route_conversion()
