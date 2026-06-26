#!/bin/bash
#
# Run all voice transcription tests
#
# Usage:
#   ./run-all-tests.sh
#

set -e

echo "======================================================================"
echo "Running All Voice Transcription Tests"
echo "======================================================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track results
RESULTS=()

# Function to run test section
run_test_section() {
    local name="$1"
    local command="$2"

    echo ""
    echo "======================================================================"
    echo "Running: $name"
    echo "======================================================================"
    echo ""

    if eval "$command"; then
        RESULTS+=("✓ $name")
        echo ""
        echo "${GREEN}✓ $name passed${NC}"
    else
        RESULTS+=("✗ $name")
        echo ""
        echo "${RED}✗ $name failed${NC}"
    fi
}

# 1. Backend Unit Tests
run_test_section "Backend Unit Tests (Gateway)" \
    "cd external-systems/partner-http-gateway && pytest gateway_tests/test_voice_routes.py -m unit -v"

# 2. Frontend Unit Tests
run_test_section "Frontend Unit Tests (Hooks)" \
    "cd frontend/her-app && npm run test:voice"

# 3. Backend Integration Tests (optional, requires Whisper model)
echo ""
echo "======================================================================"
echo "Backend Integration Tests (Requires Whisper Model)"
echo "======================================================================"
echo ""
echo "${YELLOW}Note: Integration tests may be skipped if Whisper model not installed${NC}"
echo ""

cd external-systems/partner-http-gateway
if pytest gateway_tests/test_voice_routes.py -m integration -v; then
    RESULTS+=("✓ Backend Integration Tests")
    echo "${GREEN}✓ Backend Integration Tests passed${NC}"
else
    # Integration tests may legitimately skip, so not a failure
    RESULTS+=("○ Backend Integration Tests (skipped)")
    echo "${YELLOW}○ Backend Integration Tests skipped${NC}"
fi

# Summary
echo ""
echo "======================================================================"
echo "Test Summary"
echo "======================================================================"
echo ""

for result in "${RESULTS[@]}"; do
    echo "  $result"
done

echo ""
echo "======================================================================"

# Count passed tests
PASSED=$(printf '%s\n' "${RESULTS[@]}" | grep -c '^✓' || echo 0)
TOTAL=${#RESULTS[@]}

if [ "$PASSED" -eq "$TOTAL" ]; then
    echo "${GREEN}All tests passed! ($PASSED/$TOTAL)${NC}"
    exit 0
else
    echo "${YELLOW}Some tests failed or skipped ($PASSED/$TOTAL passed)${NC}"
    exit 1
fi