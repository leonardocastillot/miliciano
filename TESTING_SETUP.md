# Testing Setup - Miliciano

## Prerequisites

To run tests, install pytest and dependencies:

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3-pytest python3-pytest-cov python3-pytest-mock

# OR with pip (if available)
pip3 install --user -r requirements-dev.txt
```

## Running Tests

### All tests
```bash
cd /home/leonard/miliciano
pytest
```

### With coverage
```bash
pytest --cov=miliciano-poc/bin --cov-report=html --cov-report=term
```

### Specific test file
```bash
pytest tests/test_validators.py
pytest tests/test_policy.py
pytest tests/test_integration.py
```

### By marker
```bash
# Only unit tests
pytest -m unit

# Only security tests
pytest -m security

# Only integration tests
pytest -m integration
```

## Test Structure

```
tests/
├── __init__.py
├── conftest.py           # Fixtures and configuration
├── test_validators.py    # Input validation tests (150+ tests)
├── test_policy.py        # Policy engine tests (90+ tests)
└── test_integration.py   # Integration tests (40+ tests)
```

## Coverage Target

**Target**: >70% code coverage

**Current modules covered**:
- `miliciano_validators.py` - Input validation
- `miliciano_policy.py` - Policy engine
- `miliciano_runtime.py` - Core runtime (partial)
- `miliciano_controls.py` - Controls (partial)
- `miliciano_setup.py` - Setup (partial)

## Test Categories

### Unit Tests (`-m unit`)
Fast, isolated tests for individual functions.

### Integration Tests (`-m integration`)
Tests that verify component interactions.

### Security Tests (`-m security`)
Tests that verify security controls work correctly.

### Slow Tests (`-m slow`)
Long-running tests (setup, full workflows).

## Manual Testing

If pytest not available, verify syntax:

```bash
cd /home/leonard/miliciano

# Check Python syntax
python3 -m py_compile miliciano-poc/bin/miliciano_validators.py
python3 -m py_compile miliciano-poc/bin/miliciano_policy.py

# Run module self-tests
python3 miliciano-poc/bin/miliciano_validators.py
python3 miliciano-poc/bin/miliciano_policy.py
```

## Expected Test Results

### test_validators.py
- **Total tests**: ~150
- **Expected pass**: 100%
- **Coverage**: >95%

Tests for:
- Provider name validation
- Model spec validation
- Route name validation
- URL validation
- Prompt sanitization
- API key validation
- Command args validation
- Security bypass attempts

### test_policy.py
- **Total tests**: ~90
- **Expected pass**: 100%
- **Coverage**: >90%

Tests for:
- SimplePolicy pattern matching
- PolicyEngine initialization
- Policy modes (enforce/audit/disabled)
- Nemoclaw integration (mocked)
- Audit logging
- Security scenarios

### test_integration.py
- **Total tests**: ~40
- **Expected pass**: 100%
- **Coverage**: N/A (integration)

Tests for:
- End-to-end security flow
- Safe command execution
- Dangerous command blocking
- Audit trail creation
- Download verification
- Regression tests

## Continuous Integration

Add to CI pipeline (Phase 6):

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: pip install -r requirements-dev.txt
      - name: Run tests
        run: pytest
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Known Issues

1. **Pytest not installed**: Install with apt or pip
2. **Import errors**: Add `miliciano-poc/bin` to PYTHONPATH
3. **Fixture issues**: Check conftest.py loaded
4. **Coverage low**: Some modules have mocked dependencies

## Debugging Tests

### Verbose output
```bash
pytest -vv
```

### Show print statements
```bash
pytest -s
```

### Stop on first failure
```bash
pytest -x
```

### Run specific test
```bash
pytest tests/test_validators.py::TestValidateProvider::test_valid_provider_simple
```

### Debug with ipdb
```bash
pip install ipdb
# Add breakpoint() in test
pytest
```

## Next Steps

1. Install pytest: `sudo apt install python3-pytest`
2. Run full test suite: `pytest`
3. Check coverage: `pytest --cov`
4. Fix any failing tests
5. Add more tests as needed
