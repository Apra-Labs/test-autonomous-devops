"""
CASE 2 Test: Multi-bug scenario requiring multiple attempts

Bug 1: Missing json import
Bug 2: Missing calculate_age function
Bug 3: Typo in function name (formatt_greeting instead of format_greeting)
"""
from datetime import datetime

def formatt_greeting(name, birth_year):
    """Has typo in name and missing dependencies"""
    age = calculate_age(birth_year)  # Bug 2: function doesn't exist

    # Bug 1: json not imported
    data = json.dumps({
        "name": name,
        "age": age
    })
    return data

if __name__ == "__main__":
    result = formatt_greeting("Test", 1990)
    print(result)
