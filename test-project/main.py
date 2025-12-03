"""
Test Scenario 2: Multiple bugs requiring 2-3 attempts

BUG 1: Missing json import
BUG 2: Wrong function name used
BUG 3: Undefined variable
"""
from datetime import datetime

def calculate_age(birth_year):
    """Calculate age from birth year"""
    current_year = datetime.now().year
    return current_year - birth_year

def format_user_data(name, birth_year):
    """Format user data as JSON"""
    age = calculate_age(birth_year)

    # BUG 1: Missing import for json module
    data = json.dumps({
        "name": name,
        "age": age,
        "timestamp": datetime.now().isoformat(),
        "status": user_status  # BUG 3: Undefined variable
    })
    return data

if __name__ == "__main__":
    # BUG 2: Wrong function name (should be format_user_data)
    result = format_greeting("Test User", 1990)
    print(result)
