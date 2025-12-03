"""
Complex test module for autonomous agent testing

BUG: Missing imports and utility function (intentional for testing multi-turn investigation)
"""
from datetime import datetime

def calculate_age(birth_year):
    """Calculate age from birth year"""
    current_year = datetime.now().year
    age = current_year - birth_year
    return age

def format_user_data(name, birth_year, location):
    """Format user data with validation - HAS BUGS: missing imports and undefined function"""
    age = calculate_age(birth_year)

    # BUG 1: json module not imported
    user_data = {
        "name": name,
        "age": age,
        "location": location,
        "timestamp": datetime.now().isoformat()
    }

    # BUG 2: undefined function 'validate_location' - should exist in utils module
    if not validate_location(location):
        raise ValueError(f"Invalid location: {location}")

    # BUG 3: Missing import for json.dumps
    return json.dumps(user_data, indent=2)

if __name__ == "__main__":
    result = format_user_data("Test User", 1990, "San Francisco")
    print(result)
