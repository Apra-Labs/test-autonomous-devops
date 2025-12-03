"""
Tests for main.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from main import calculate_age, format_user_data

def test_calculate_age():
    """Test age calculation"""
    age = calculate_age(1990)
    assert age > 0, "Age should be positive"
    print(f"✓ Age calculation works: {age} years")

def test_format_user_data():
    """Test user data formatting"""
    result = format_user_data("Alice", 1995, "New York")
    assert "Alice" in result, "Name should be in result"
    assert "New York" in result, "Location should be in result"
    print(f"✓ Format user data works: {result}")

if __name__ == "__main__":
    print("Running tests...")
    test_calculate_age()
    test_format_user_data()
    print("\n✅ All tests passed!")
