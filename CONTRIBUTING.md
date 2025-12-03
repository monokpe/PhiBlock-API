# Contributing to Guardrails

Thank you for contributing to Guardrails! This document provides guidelines to maintain code quality and prevent "AI slop" (verbose, unnecessary, or low-quality code).

## Code Quality Standards

### 1. Code Formatting
We use **black** for consistent code formatting:
```bash
black app/ tests/ workers/
```

### 2. Import Organization
We use **isort** to organize imports:
```bash
isort app/ tests/ workers/
```

### 3. Type Hints
- Use type hints for all function parameters and return values
- Run `mypy` to check type consistency:
```bash
mypy app/ workers/
```

### 4. Linting
- Code must pass `flake8` checks:
```bash
flake8 app/ tests/ workers/ --max-line-length=100
```

## Anti-Patterns to Avoid

### ❌ Overly Verbose Names
```python
# Bad
def get_user_from_database_by_user_id_with_error_handling(user_id: str):
    pass

# Good
def get_user(user_id: str) -> Optional[User]:
    pass
```

### ❌ Unnecessary Comments
```python
# Bad
# This function adds two numbers together
def add(a: int, b: int) -> int:
    # Return the sum of a and b
    return a + b

# Good
def add(a: int, b: int) -> int:
    return a + b
```

### ❌ Dead Code
- No commented-out code
- No unused imports
- No unused variables

### ❌ Complex Functions
- Keep cyclomatic complexity under 10
- Break down complex functions into smaller helpers

### ❌ Print Statements
- Use proper logging instead of `print()`
- Use `logger.info()`, `logger.debug()`, etc.

## Pre-commit Hooks

Install pre-commit hooks to automatically check code before committing:

```bash
pip install pre-commit
pre-commit install
```

This will run:
- black (formatting)
- isort (import sorting)
- flake8 (linting)
- mypy (type checking)
- trailing whitespace removal
- end-of-file fixer

## Running Quality Checks Locally

Run all quality checks before pushing:

```bash
# Format code
black app/ tests/ workers/
isort app/ tests/ workers/

# Lint
flake8 app/ tests/ workers/ --max-line-length=100

# Type check
mypy app/ workers/

# Check complexity
radon cc app/ -a -nb

# Find dead code
vulture app/ workers/

# Security scan
bandit -r app/ workers/
```

Or use the convenience script:
```bash
bash scripts/quality_check.sh
```

## Pull Request Checklist

Before submitting a PR, ensure:

- [ ] Code is formatted with black
- [ ] Imports are sorted with isort
- [ ] All tests pass (`pytest`)
- [ ] No flake8 warnings
- [ ] Type hints are present and mypy passes
- [ ] No commented-out code
- [ ] No print statements (use logging)
- [ ] Functions have docstrings
- [ ] Complexity is under threshold
- [ ] No security issues (bandit)

## Code Review Guidelines

Reviewers should check for:

1. **Clarity** - Is the code easy to understand?
2. **Simplicity** - Is this the simplest solution?
3. **Necessity** - Is all this code needed?
4. **Performance** - Are there obvious performance issues?
5. **Security** - Are there security concerns?
6. **Tests** - Are there adequate tests?

## Questions?

If you have questions about these guidelines, please open an issue or ask in the PR.
