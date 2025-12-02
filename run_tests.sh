#!/bin/bash
# Run all tests with coverage

echo "========================================"
echo "Autonomous DevOps Agent - Test Suite"
echo "========================================"
echo ""

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo "ERROR: pytest not found. Installing dependencies..."
    pip install -r requirements.txt
fi

echo "Running unit tests..."
echo ""

# Run tests with coverage
pytest tests/ \
    --verbose \
    --cov=agent \
    --cov-report=term-missing \
    --cov-report=html \
    "$@"

exit_code=$?

echo ""
if [ $exit_code -eq 0 ]; then
    echo "✅ All tests passed!"
    echo ""
    echo "Coverage report generated in htmlcov/index.html"
else
    echo "❌ Some tests failed!"
fi

exit $exit_code
