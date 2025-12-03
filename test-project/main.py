"""
Test Scenario 3: Simple 2-bug scenario for CASE 2 testing

BUG 1: Missing json import (will fail first)
BUG 2: Undefined variable (will fail after BUG 1 is fixed)
"""
from datetime import datetime

def format_user_data(name, birth_year):
    """Format user data as JSON"""
    current_year = datetime.now().year
    age = current_year - birth_year

    # BUG 1: Missing import for json module
    data = json.dumps({
        "name": name,
        "age": age,
        "timestamp": datetime.now().isoformat(),
        "status": user_status  # BUG 2: Undefined variable
    })
    return data

if __name__ == "__main__":
    result = format_user_data("Test User", 1990)
    print(result)
