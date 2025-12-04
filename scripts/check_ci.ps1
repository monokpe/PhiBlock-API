# Local CI Check Script
# Run this before pushing to verify all CI checks will pass

Write-Host "========================================" -ForegroundColor Green
Write-Host "  Running Local CI Checks" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green

$failed = 0

# 1. Black (code formatting)
Write-Host "`n[1/6] Checking code formatting (black)..." -ForegroundColor Cyan
.\new_venv\Scripts\black --check app/ workers/ tests/
if ($LASTEXITCODE -ne 0) { $failed++ }

# 2. isort (import sorting)
Write-Host "`n[2/6] Checking import sorting (isort)..." -ForegroundColor Cyan
.\new_venv\Scripts\isort --check-only app/ workers/ tests/
if ($LASTEXITCODE -ne 0) { $failed++ }

# 3. flake8 (linting)
Write-Host "`n[3/6] Running linter (flake8)..." -ForegroundColor Cyan
.\new_venv\Scripts\flake8 app/ workers/ tests/ --max-line-length=100 --extend-ignore=E203,W503,D --count
if ($LASTEXITCODE -ne 0) { $failed++ }

# 4. mypy (type checking)
Write-Host "`n[4/6] Running type checker (mypy)..." -ForegroundColor Cyan
.\new_venv\Scripts\mypy app/ workers/ --ignore-missing-imports --check-untyped-defs
if ($LASTEXITCODE -ne 0) { $failed++ }

# 5. bandit (security)
Write-Host "`n[5/6] Running security scan (bandit)..." -ForegroundColor Cyan
.\new_venv\Scripts\bandit -r app/ workers/ -ll
if ($LASTEXITCODE -ne 0) { $failed++ }

# 6. radon (complexity)
Write-Host "`n[6/6] Checking code complexity (radon)..." -ForegroundColor Cyan
.\new_venv\Scripts\radon cc app/ workers/ -a -nb --total-average

# Summary
Write-Host "`n========================================" -ForegroundColor Green
if ($failed -eq 0) {
    Write-Host "  ✅ All CI checks passed!" -ForegroundColor Green
    Write-Host "  Safe to push to GitHub" -ForegroundColor Green
} else {
    Write-Host "  ❌ $failed check(s) failed" -ForegroundColor Red
    Write-Host "  Fix errors before pushing" -ForegroundColor Red
}
Write-Host "========================================" -ForegroundColor Green

exit $failed
