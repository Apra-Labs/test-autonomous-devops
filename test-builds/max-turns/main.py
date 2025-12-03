"""
Multi-turn test: Complex interdependent modules

This should trigger multiple investigation turns as LLM
discovers dependencies across multiple files.
"""
from utils.validator import validate_input
from utils.processor import process_data
from utils.formatter import format_output

def main(data):
    """Process data through multiple steps"""
    validated = validate_input(data)
    processed = process_data(validated)
    formatted = format_output(processed)
    return formatted

if __name__ == "__main__":
    result = main({"name": "test"})
    print(result)
