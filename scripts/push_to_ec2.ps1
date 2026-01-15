# PhiBlock Local Push Script
# Use this to upload your code and trigger deployment on EC2.

param (
    [Parameter(Mandatory=$true)]
    [string]$EC2_IP,

    [Parameter(Mandatory=$true)]
    [string]$SSH_KEY_PATH,

    [string]$EC2_USER = "ec2-user"
)

$ErrorActionPreference = "Stop"

# Check if SSH Key exists
if (!(Test-Path $SSH_KEY_PATH)) {
    Write-Error "❌ Error: SSH Key not found at: $SSH_KEY_PATH"
    exit 1
}


# Use common SSH options for demo convenience (array format for PowerShell)
$SSH_OPTS = "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"


Write-Host "🚀 Preparing PhiBlock for deployment..." -ForegroundColor Cyan

$ZipFile = "phiblock.zip"
if (Test-Path $ZipFile) { Remove-Item $ZipFile }

Write-Host "📦 Creating archive..."
$FilesToInclude = @("app", "workers", "alembic", "scripts", "alembic.ini", "Dockerfile", "docker-compose.yml", "requirements.txt", "requirements-pinned.txt", "entrypoint.sh", ".env.example", "pyproject.toml")
$ValidFiles = $FilesToInclude | Where-Object { Test-Path $_ }

if ($ValidFiles.Count -eq 0) {
    Write-Error "No valid project files found to archive! Are you in the right directory?"
    exit 1
}

Compress-Archive -Path $ValidFiles -DestinationPath $ZipFile


# 2. Upload to EC2
Write-Host "📤 Uploading to EC2 ($EC2_IP)..." -ForegroundColor Cyan
scp $SSH_OPTS -i "$SSH_KEY_PATH" "$ZipFile" "$($EC2_USER)@$($EC2_IP):~/"

# 3. Upload the deployment script specifically (to ensure it's there)
Write-Host "📤 Uploading deployment script..."
scp $SSH_OPTS -i "$SSH_KEY_PATH" "scripts/deploy_ec2.sh" "$($EC2_USER)@$($EC2_IP):~/deploy_ec2.sh"

# 4. Run deployment on EC2
Write-Host "🛠️ Running deployment script on remote server..." -ForegroundColor Green
ssh $SSH_OPTS -i "$SSH_KEY_PATH" "$($EC2_USER)@$($EC2_IP)" "chmod +x ~/deploy_ec2.sh && ~/deploy_ec2.sh"


# 5. Cleanup
if (Test-Path $ZipFile) { Remove-Item $ZipFile }

Write-Host "`n✨ Done! Your app should be live soon." -ForegroundColor Green
Write-Host "🔗 Check: http://${EC2_IP}:8000/docs" -ForegroundColor Cyan
