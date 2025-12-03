import json
from datetime import datetime

def calculate_age(birth_year):
    """Calculate age based on birth year."""
    current_year = datetime.now().year
    age = current_year - birth_year
    return age

def format_greeting(name, birth_year):
    """Format a greeting with name and age."""
    age = calculate_age(birth_year)
    greeting = f"Hello, {name}! You are {age} years old."
    
    # Format as JSON for API response
    data = json.dumps({
        "greeting": greeting,
        "name": name,
        "age": age
    })
    return data

if __name__ == "__main__":
    result = format_greeting("World", 2000)
    print(result)
