AGENT_CARD = {
    "name": "Unit Converter",
    "description": "Converts between common units of measurement including temperature, distance, and weight.",
    "url": "http://localhost:5000",
    "preferredTransport": "JSONRPC",
    "additionalInterfaces": [
        {
            "url": "http://localhost:5000",
            "transport": "JSONRPC",
        }
    ],
    "version": "1.0.0",
    "protocolVersion": "0.3.0",
    "capabilities": {
        "streaming": False,
        "pushNotifications": False
    },
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["text/plain"],
    "skills": [
        {
            "id": "temperature",
            "name": "Temperature Conversion",
            "description": "Convert between Fahrenheit, Celsius, and Kelvin.",
            "tags": ["temperature", "conversion", "units"],
            "examples": [
                "Convert 100 Fahrenheit to Celsius",
                "32°F in Kelvin"
            ]
        },
        {
            "id": "distance",
            "name": "Distance Conversion",
            "description": "Convert between miles, kilometers, meters, and feet.",
            "tags": ["distance", "length", "conversion", "units"],
            "examples": [
                "Convert 5 miles to kilometers",
                "1000 meters in feet"
            ]
        },
        {
            "id": "weight",
            "name": "Weight Conversion",
            "description": "Convert between pounds, kilograms, ounces, and grams.",
            "tags": ["weight", "mass", "conversion", "units"],
            "examples": [
                "Convert 150 pounds to kilograms",
                "250 grams in ounces"
            ]
        }
    ],
    "provider": {
        "organization": "A2A Tutorial"
    }
}
