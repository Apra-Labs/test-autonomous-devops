"""
Simple Python application for testing autonomous agent
"""
from datetime import datetime

def calculate_age(birth_year):
    """Calculate age from birth year"""
    current_year = datetime.now().year
    return current_year - birth_year

def format_greeting(name, birth_year):
    """Format a greeting with age"""
    age = calculate_age(birth_year)
    # BUG: Missing import for json module
    data = json.dumps({
        "name": name,
        "age": age,
        "timestamp": datetime.now().isoformat()
    })
    return data

if __name__ == "__main__":
    result = format_greeting("Test User", 1990)
    print(result)
