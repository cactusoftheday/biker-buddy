import overpy

# Initialize Overpass API
api = overpy.Overpass()

lat, lon = 51.043013, -114.216861
# Define a buffer in degrees (about ~300m)
buffer = 0.003

south = lat - buffer
north = lat + buffer
west = lon - buffer
east = lon + buffer
query = f"""
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

# Run the query
result = api.query(query)

# Print all nodes from the result
for way in result.ways:
    print(f"Way ID: {way.id}")
    print(f"  highway: {way.tags.get('highway', 'N/A')}, maxspeed: {way.tags.get('maxspeed', 'N/A')}")
    for node in way.nodes:
        print(f"  Node ID: {node.id}, Lat: {node.lat}, Lon: {node.lon}")