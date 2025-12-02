"""
Tests for main.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from main import calculate_age, format_greeting

def test_calculate_age():
    """Test age calculation"""
    age = calculate_age(1990)
    assert age > 0, "Age should be positive"
    print(f"✓ Age calculation works: {age} years")

def test_format_greeting():
    """Test greeting formatting"""
    result = format_greeting("Alice", 1995)
    assert "Alice" in result, "Name should be in result"
    print(f"✓ Format greeting works: {result}")

if __name__ == "__main__":
    print("Running tests...")
    test_calculate_age()
    test_format_greeting()
    print("\n✅ All tests passed!")
