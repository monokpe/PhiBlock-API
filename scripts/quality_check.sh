#!/bin/bash
# Quality check script - Run all code quality tools

set -e

echo "🔍 Running code quality checks..."
echo ""

echo "1️⃣ Formatting with black..."
black --check app/ tests/ workers/ || {
    echo "❌ Black formatting failed. Run: black app/ tests/ workers/"
    exit 1
}
echo "✅ Black formatting passed"
echo ""

echo "2️⃣ Sorting imports with isort..."
isort --check-only app/ tests/ workers/ || {
    echo "❌ Import sorting failed. Run: isort app/ tests/ workers/"
    exit 1
}
echo "✅ Import sorting passed"
echo ""

echo "3️⃣ Linting with flake8..."
flake8 app/ tests/ workers/ --max-line-length=100 --extend-ignore=E203,W503 || {
    echo "❌ Flake8 linting failed"
    exit 1
}
echo "✅ Flake8 linting passed"
echo ""

echo "4️⃣ Type checking with mypy..."
mypy app/ workers/ --ignore-missing-imports --check-untyped-defs || {
    echo "❌ Type checking failed"
    exit 1
}
echo "✅ Type checking passed"
echo ""

echo "5️⃣ Checking complexity with radon..."
radon cc app/ workers/ -a -nb --total-average || {
    echo "❌ Complexity check failed"
    exit 1
}
echo "✅ Complexity check passed"
echo ""

echo "6️⃣ Finding dead code with vulture..."
vulture app/ workers/ --min-confidence 80 || {
    echo "⚠️  Potential dead code found (review manually)"
}
echo ""

echo "7️⃣ Security scan with bandit..."
bandit -r app/ workers/ -ll || {
    echo "❌ Security issues found"
    exit 1
}
echo "✅ Security scan passed"
echo ""

echo "8️⃣ Checking for AI slop patterns..."
# No print statements in production code
if grep -r "print(" app/ workers/ --include="*.py" | grep -v "# noqa"; then
    echo "❌ Found print() statements in production code"
    exit 1
fi
echo "✅ No print statements found"
echo ""

echo "🎉 All quality checks passed!"
