import re


UNITS = {
    "temperature": {
        "fahrenheit": {"to_base": lambda f: (f - 32) * 5 / 9, "from_base": lambda c: c * 9 / 5 + 32},
        "celsius": {"to_base": lambda c: c, "from_base": lambda c: c},
        "kelvin": {"to_base": lambda k: k - 273.15, "from_base": lambda c: c + 273.15},
    },
    "distance": {
        "miles": {"to_base": lambda m: m * 1609.344, "from_base": lambda m: m / 1609.344},
        "kilometers": {"to_base": lambda k: k * 1000, "from_base": lambda m: m / 1000},
        "meters": {"to_base": lambda m: m, "from_base": lambda m: m},
        "feet": {"to_base": lambda f: f * 0.3048, "from_base": lambda m: m / 0.3048},
    },
    "weight": {
        "pounds": {"to_base": lambda p: p * 453.592, "from_base": lambda g: g / 453.592},
        "kilograms": {"to_base": lambda k: k * 1000, "from_base": lambda g: g / 1000},
        "ounces": {"to_base": lambda o: o * 28.3495, "from_base": lambda g: g / 28.3495},
        "grams": {"to_base": lambda g: g, "from_base": lambda g: g},
    },
}

ALIASES = {
    "f": "fahrenheit", "°f": "fahrenheit", "fahr": "fahrenheit",
    "c": "celsius", "°c": "celsius",
    "k": "kelvin",
    "mi": "miles", "mile": "miles",
    "km": "kilometers", "kilometer": "kilometers",
    "m": "meters", "meter": "meters",
    "ft": "feet", "foot": "feet",
    "lb": "pounds", "lbs": "pounds", "pound": "pounds",
    "kg": "kilograms", "kilogram": "kilograms",
    "oz": "ounces", "ounce": "ounces",
    "g": "grams", "gram": "grams",
}


def _resolve_unit(name):
    """Resolve a unit name or alias to (category, canonical_name)."""
    name = name.lower().strip().rstrip(".")
    if name in ALIASES:
        name = ALIASES[name]
    for category, units in UNITS.items():
        if name in units:
            return category, name
    return None, None


def _parse_input(text):
    """Parse natural language conversion request.

    Expected patterns:
      "Convert 100 fahrenheit to celsius"
      "100 F to C"
      "100°F in Kelvin"
    """
    text = text.strip()
    pattern = r"(?:convert\s+)?(-?\d+(?:\.\d+)?)\s*°?\s*(\w+)\s+(?:to|in)\s+°?\s*(\w+)"
    match = re.search(pattern, text, re.IGNORECASE)

    if not match:
        raise ValueError(
            "Could not parse your request. Try something like: "
            "'Convert 100 Fahrenheit to Celsius'"
        )

    value = float(match.group(1))
    from_unit = match.group(2)
    to_unit = match.group(3)
    return value, from_unit, to_unit


def convert(text):
    """Parse a conversion request and return the result as a string."""
    value, from_name, to_name = _parse_input(text)

    from_category, from_unit = _resolve_unit(from_name)
    to_category, to_unit = _resolve_unit(to_name)

    if from_category is None:
        raise ValueError(f"Unknown unit: {from_name}")
    if to_category is None:
        raise ValueError(f"Unknown unit: {to_name}")
    if from_category != to_category:
        raise ValueError(
            f"Cannot convert between {from_name} ({from_category}) "
            f"and {to_name} ({to_category})"
        )

    # Convert: source --> base unit --> target
    base_value = UNITS[from_category][from_unit]["to_base"](value)
    result = UNITS[from_category][to_unit]["from_base"](base_value)

    return f"{value} {from_unit} = {result:.4g} {to_unit}"
