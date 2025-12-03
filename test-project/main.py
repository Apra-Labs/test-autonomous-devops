"""Main module with utility functions."""

from datetime import datetime


def calculate_age(birth_year: int) -> int:
    """Calculate age based on birth year.
    
    Args:
        birth_year: The year of birth
        
    Returns:
        The calculated age in years
    """
    current_year = datetime.now().year
    return current_year - birth_year


def format_greeting(name: str) -> str:
    """Format a greeting message.
    
    Args:
        name: The name to greet
        
    Returns:
        A formatted greeting string
    """
    return f"Hello, {name}!"


if __name__ == "__main__":
    # Example usage
    age = calculate_age(1990)
    print(f"Age: {age}")
    print(format_greeting("World"))
