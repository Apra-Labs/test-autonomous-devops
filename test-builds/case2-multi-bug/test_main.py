"""Test for CASE 2 scenario"""
from main import format_greeting  # Note: should be format_greeting, not formatt_greeting

def test_greeting():
    result = format_greeting("Alice", 1995)
    assert "Alice" in result
    print("✓ Test passed")

if __name__ == "__main__":
    test_greeting()
    print("All tests passed!")
