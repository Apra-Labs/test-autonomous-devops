import json
from datetime import datetime

def calculate_age(birth_year):
    current_year = datetime.now().year
    return current_year - birth_year

def greet(name):
    return f"Hello, {name}!"

def format_greeting(name, birth_year):
    age = calculate_age(birth_year)
    greeting = greet(name)
    
    # Format as JSON
    data = json.dumps({
        "greeting": greeting,
        "age": age,
        "name": name
    })
    return data

if __name__ == "__main__":
    print("Testing the application...")
    result = format_greeting("Test User", 1990)
    print(result)
