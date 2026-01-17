# PhiBlock AWS EC2 Deployment Guide

A step-by-step guide to deploy PhiBlock to AWS EC2, based on our actual deployment session on January 2-7, 2026.

> **Target Audience**: Developers familiar with programming basics who want to deploy PhiBlock to AWS for demo or production.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Prerequisites](#2-prerequisites)
3. [EC2 Instance Setup](#3-ec2-instance-setup)
4. [Deploy PhiBlock](#4-deploy-phiblock)
5. [Post-Deployment Configuration](#5-post-deployment-configuration)
6. [Create Tenant and API Key](#6-create-tenant-and-api-key)
7. [Test All Endpoints](#7-test-all-endpoints)
8. [Access the Dashboard](#8-access-the-dashboard)
9. [Record a Video Demo with OBS](#9-record-a-video-demo-with-obs)
10. [Maintenance Commands](#10-maintenance-commands)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Overview

### What This Guide Covers
- Deploying PhiBlock to an existing AWS EC2 instance
- Using the automated deployment scripts
- Testing all API endpoints
- Accessing the analytics dashboard
- Recording a demo video with OBS

### Current Deployment Details
- **EC2 IP Address**: 98.84.46.28
- **Instance Type**: t3.medium
- **OS**: Amazon Linux 2023
- **Key Pair File**: `C:\Users\DELL\Downloads\phiblock-keypair.pem`

---

## 2. Prerequisites

### Step 2.1: Ensure You Have an EC2 Instance Running

1. Log in to AWS Console: https://console.aws.amazon.com
2. Navigate to EC2 → Instances
3. Verify your instance is in "Running" state
4. Note the **Public IPv4 address** (e.g., `98.84.46.28`)

### Step 2.2: Ensure Security Group Allows Port 8000

1. In EC2 Console, click on your instance
2. Click the Security tab
3. Click on the Security Group link
4. Click "Edit inbound rules"
5. Add rule:
   - Type: Custom TCP
   - Port range: 8000
   - Source: 0.0.0.0/0 (or your IP for security)
6. Click "Save rules"

### Step 2.3: Ensure You Have Your SSH Key

Verify your key file exists:
```powershell
Test-Path "C:\Users\DELL\Downloads\phiblock-keypair.pem"
```
Should return `True`.

### Step 2.4: Ensure Sufficient Disk Space (20GB+)

Our deployment failed initially with "No space left on device" because the default 8GB EBS volume was too small.

**To check/increase EBS volume:**
1. Go to EC2 Console → Volumes (left sidebar)
2. Select the volume attached to your instance
3. Actions → Modify Volume
4. Change Size to at least **20 GB**
5. Click Modify

**After modifying, SSH into EC2 and extend the filesystem:**
```bash
ssh -i "C:\Users\DELL\Downloads\phiblock-keypair.pem" ec2-user@98.84.46.28

# On EC2:
sudo growpart /dev/xvda 1
sudo xfs_growfs /
df -h  # Verify new size
```

---

## 3. EC2 Instance Setup

The deployment script handles most setup automatically, but here's what happens:

### Step 3.1: What the Deploy Script Installs
- Docker
- Docker Compose
- Docker Buildx plugin
- unzip

### Step 3.2: Manual Pre-check (Optional)

SSH into your instance to verify it's ready:
```powershell
ssh -i "C:\Users\DELL\Downloads\phiblock-keypair.pem" ec2-user@98.84.46.28
```

Once connected:
```bash
# Check available space
df -h

# Check if Docker is installed (might not be yet)
docker --version

# Exit SSH
exit
```

---

## 4. Deploy PhiBlock

### Step 4.1: Navigate to Project Directory

Open PowerShell and navigate to your project:
```powershell
cd "C:\Users\DELL\Desktop\personal projects\PhiBlock\PhiBlock"
```

### Step 4.2: Run the Deployment Script

Execute the deployment script:
```powershell
.\scripts\push_to_ec2.ps1 -EC2_IP "98.84.46.28" -SSH_KEY_PATH "C:\Users\DELL\Downloads\phiblock-keypair.pem"
```

### Step 4.3: What the Script Does

1. **Creates archive** (`phiblock.zip`) containing:
   - `app/` - Main application code
   - `workers/` - Celery worker tasks
   - `alembic/` - Database migrations
   - `scripts/` - Deployment scripts
   - `Dockerfile`, `docker-compose.yml`
   - `requirements.txt`, `entrypoint.sh`
   - `.env.example`

2. **Uploads to EC2** via SCP

3. **Runs `deploy_ec2.sh`** on EC2 which:
   - Installs Docker, Docker Compose, Docker Buildx
   - Unpacks the application
   - Creates `.env` from `.env.example` with random SECRET_KEY
   - Builds Docker images
   - Starts containers (api, worker, db, redis)
   - Waits for API health check

### Step 4.4: Expected Output

```
🚀 Preparing PhiBlock for deployment...
📦 Creating archive...
📤 Uploading to EC2 (98.84.46.28)...
📤 Uploading deployment script...
🛠️ Running deployment script on remote server...
🚀 Starting PhiBlock Deployment...
📦 Checking dependencies...
🐳 Starting Docker...
🔧 Ensuring Docker Buildx is available...
📂 Unpacking PhiBlock...
⚙️ Configuring environment...
✅ Created .env with generated SECRET_KEY
🚀 Building and starting containers...
⏳ Waiting for API to start...
..
✅ Deployment Complete!
🌐 URL: http://98.84.46.28:8000
📚 API Docs: http://98.84.46.28:8000/docs

✨ Done! Your app should be live soon.
🔗 Check: http://98.84.46.28:8000/docs
```

### Step 4.5: Verify Deployment

Open in your browser:
- **API Docs**: http://98.84.46.28:8000/docs
- **Health Check**: http://98.84.46.28:8000/v1/health

---

## 5. Post-Deployment Configuration

### Step 5.1: Configure Environment Variables (Optional)

The deployment creates a basic `.env` file. For full functionality, you may want to add:

```bash
ssh -i "C:\Users\DELL\Downloads\phiblock-keypair.pem" ec2-user@98.84.46.28

# Edit the .env file
nano ~/phiblock_temp/.env
```

Add your API keys:
```env
# Stripe (optional)
STRIPE_SECRET_KEY=sk_test_your_key_here
STRIPE_PRICE_ID=price_your_price_id

# Sentry (optional)
SENTRY_DSN=https://your-dsn@sentry.io/project-id
```

Save and restart:
```bash
cd ~/phiblock_temp
sudo docker-compose restart api worker
exit
```

### Step 5.2: Fix Dashboard (Critical)

The dashboard file needs to be renamed inside the container:

```powershell
ssh -i "C:\Users\DELL\Downloads\phiblock-keypair.pem" ec2-user@98.84.46.28 "sudo docker exec phiblock_temp-api-1 mv /app/app/static/dashboard.html /app/app/static/index.html && sudo docker-compose -f ~/phiblock_temp/docker-compose.yml restart api"
```

This command:
1. Renames `dashboard.html` to `index.html` inside the container
2. Restarts the API container

---

## 6. Create Tenant and API Key

### Step 6.1: Create a Tenant

Using curl from your local machine:
```bash
curl -X POST "http://98.84.46.28:8000/v1/tenants" \
  -H "Content-Type: application/json" \
  -d '{"name": "Demo Company", "plan": "pro"}'
```

Or use PowerShell:
```powershell
Invoke-RestMethod -Uri "http://98.84.46.28:8000/v1/tenants" -Method POST -ContentType "application/json" -Body '{"name": "Demo Company", "plan": "pro"}'
```

### Step 6.2: Create Customer and API Key

Run this command to create a customer and API key:

```powershell
ssh -i "C:\Users\DELL\Downloads\phiblock-keypair.pem" ec2-user@98.84.46.28 'sudo docker exec phiblock_temp-api-1 python -c "
from app.database import SessionLocal
from app.models import Tenant, Customer, APIKey
import hashlib
import secrets

db = SessionLocal()

# Get the tenant
tenant = db.query(Tenant).first()
if not tenant:
    print(\"ERROR: Create a tenant first!\")
    exit(1)

print(f\"Using tenant: {tenant.name}\")

# Create customer
customer = db.query(Customer).filter(Customer.tenant_id == tenant.id).first()
if not customer:
    customer = Customer(
        name=\"Demo User\",
        email=\"demo@example.com\",
        tenant_id=tenant.id
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    print(f\"Created customer: {customer.name}\")

# Create API key
plain_key = secrets.token_hex(16)
hashed_key = hashlib.sha256(plain_key.encode()).hexdigest()
api_key = APIKey(
    customer_id=customer.id,
    tenant_id=tenant.id,
    key_hash=hashed_key,
    name=\"Demo API Key\"
)
db.add(api_key)
db.commit()

print(f\"\")
print(f\"YOUR API KEY: {plain_key}\")
print(f\"\")
print(\"Save this key! It cannot be retrieved later.\")
db.close()
"'
```

**Save the output API key!** You'll need it for testing and the dashboard.

---

## 7. Test All Endpoints

Replace `YOUR_API_KEY` with the key from Step 6.2.

### Step 7.1: Health Check (No Auth)
```bash
curl http://98.84.46.28:8000/v1/health
```
Expected: `{"status":"healthy","version":"0.1.0"}`

### Step 7.2: Analyze Prompt (Auth Required)
```bash
curl -X POST "http://98.84.46.28:8000/v1/analyze" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"prompt": "My email is john@example.com and my SSN is 123-45-6789"}'
```

### Step 7.3: List Tenants
```bash
curl "http://98.84.46.28:8000/v1/tenants"
```

### Step 7.4: Analytics Stats (Auth Required)
```bash
curl "http://98.84.46.28:8000/v1/analytics/stats?range=7d" \
  -H "X-API-Key: YOUR_API_KEY"
```

### Step 7.5: Performance Metrics (Auth Required)
```bash
curl "http://98.84.46.28:8000/v1/performance/health"
```

### Complete Endpoint List

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/v1/health` | GET | No | Health check |
| `/v1/analyze` | POST | Yes | Analyze prompt |
| `/v1/tenants` | GET | No | List tenants |
| `/v1/tenants` | POST | No | Create tenant |
| `/v1/tenants/{id}` | GET | No | Get tenant |
| `/v1/tenants/{id}` | PUT | No | Update tenant |
| `/v1/tenants/{id}` | DELETE | No | Delete tenant |
| `/v1/analytics/stats` | GET | Yes | Analytics stats |
| `/v1/analytics/timeseries` | GET | Yes | Traffic timeseries |
| `/v1/analytics/violations` | GET | Yes | Violations breakdown |
| `/v1/performance/health` | GET | No | Detailed health |
| `/v1/performance/metrics` | GET | Yes | System metrics |
| `/api/v1/analyze/async` | POST | No | Async analysis |
| `/api/v1/tasks/{id}` | GET | No | Task status |
| `/graphql` | POST | No | GraphQL endpoint |
| `/dashboard/` | GET | No | Dashboard UI |
| `/docs` | GET | No | Swagger UI |

---

## 8. Access the Dashboard

### Step 8.1: Open Dashboard URL

Navigate to: http://98.84.46.28:8000/dashboard/

### Step 8.2: Enter API Key

1. A modal will appear asking for your API key
2. Paste the API key from Step 6.2
3. Click "Access Dashboard"

### Step 8.3: Dashboard Features

- **Total Requests**: Count of API calls
- **Estimated Cost**: Token usage in USD
- **Attacks Blocked**: Injection attempts detected
- **Avg Latency**: Response time in ms
- **Traffic & Violations Chart**: Requests over time
- **PII Detected Chart**: Breakdown by PII type
- **Injection Types Chart**: Attack types detected

---

## 9. Record a Video Demo with OBS

### Step 9.1: Download and Install OBS

1. Go to https://obsproject.com/download
2. Download OBS Studio for Windows
3. Run the installer
4. Launch OBS Studio

### Step 9.2: Configure OBS

#### Step 9.2.1: Add Display Capture Source
1. In the "Sources" panel, click "+"
2. Select "Display Capture"
3. Name it "PhiBlock Demo"
4. Click OK
5. Select your monitor
6. Click OK

#### Step 9.2.2: Configure Output Settings
1. Click Settings (bottom right)
2. Go to "Output" tab
3. Set:
   - Output Mode: Simple
   - Recording Quality: High Quality
   - Recording Format: mp4
   - Recording Path: Choose a folder (e.g., Desktop)
4. Click Apply, then OK

#### Step 9.2.3: Configure Audio (Optional)
1. In Settings → Audio
2. Enable Desktop Audio
3. Enable Mic/Auxiliary Audio if you want voiceover

### Step 9.3: Demo Script

Follow this script while recording:

#### Scene 1: Introduction (30 seconds)
1. Open browser to http://98.84.46.28:8000/docs
2. Show the Swagger UI
3. Highlight the endpoints

#### Scene 2: Health Check (15 seconds)
1. Open http://98.84.46.28:8000/v1/health
2. Show the healthy response

#### Scene 3: Analyze Prompt (60 seconds)
1. Go to `/v1/analyze` in Swagger UI
2. Click "Try it out"
3. Enter your API key in the header
4. Enter test prompt: `My email is john@example.com and SSN is 123-45-6789`
5. Click Execute
6. Show the response with PII detected

#### Scene 4: Dashboard (60 seconds)
1. Navigate to http://98.84.46.28:8000/dashboard/
2. Enter API key
3. Show the analytics charts
4. Highlight key metrics

#### Scene 5: Conclusion (15 seconds)
1. Return to Swagger UI
2. Briefly show other endpoints

### Step 9.4: Recording

1. Click "Start Recording" in OBS
2. Follow the demo script
3. Click "Stop Recording" when done
4. Find the video in your Recording Path folder

### Step 9.5: Post-Processing (Optional)

For basic editing:
- Windows: Use the built-in Video Editor (search in Start menu)
- Professional: Use DaVinci Resolve (free) or Adobe Premiere

---

## 10. Maintenance Commands

### View Container Logs
```powershell
ssh -i "C:\Users\DELL\Downloads\phiblock-keypair.pem" ec2-user@98.84.46.28 "cd ~/phiblock_temp && sudo docker-compose logs -f --tail=100"
```

### Restart All Containers
```powershell
ssh -i "C:\Users\DELL\Downloads\phiblock-keypair.pem" ec2-user@98.84.46.28 "cd ~/phiblock_temp && sudo docker-compose restart"
```

### Stop All Containers
```powershell
ssh -i "C:\Users\DELL\Downloads\phiblock-keypair.pem" ec2-user@98.84.46.28 "cd ~/phiblock_temp && sudo docker-compose down"
```

### Clear Docker Cache
```powershell
ssh -i "C:\Users\DELL\Downloads\phiblock-keypair.pem" ec2-user@98.84.46.28 "sudo docker system prune -af && sudo docker volume prune -f"
```

### Redeploy After Code Changes
```powershell
.\scripts\push_to_ec2.ps1 -EC2_IP "98.84.46.28" -SSH_KEY_PATH "C:\Users\DELL\Downloads\phiblock-keypair.pem"
```

### SSH Interactive Session
```powershell
ssh -i "C:\Users\DELL\Downloads\phiblock-keypair.pem" ec2-user@98.84.46.28
```

---

## 11. Troubleshooting

### Problem: Deployment script fails with "No space left on device"

**Cause**: Default 8GB EBS volume is too small.

**Solution**:
1. Increase EBS volume to 20GB in AWS Console
2. SSH in and extend filesystem:
   ```bash
   sudo growpart /dev/xvda 1
   sudo xfs_growfs /
   ```
3. Redeploy

### Problem: "compose build requires buildx 0.17 or later"

**Cause**: Docker Buildx plugin not installed.

**Solution**: The deploy script now handles this automatically. If it still fails:
```bash
ssh -i "C:\Users\DELL\Downloads\phiblock-keypair.pem" ec2-user@98.84.46.28
sudo mkdir -p /usr/libexec/docker/cli-plugins
sudo curl -sSL "https://github.com/docker/buildx/releases/download/v0.19.3/buildx-v0.19.3.linux-amd64" -o /usr/libexec/docker/cli-plugins/docker-buildx
sudo chmod +x /usr/libexec/docker/cli-plugins/docker-buildx
```

### Problem: "permission denied: ./entrypoint.sh"

**Cause**: Windows CRLF line endings in entrypoint.sh.

**Solution**: The Dockerfile now includes `sed -i 's/\r$//' entrypoint.sh` to fix this automatically.

If it persists after a volume mount override, run:
```powershell
ssh -i "C:\Users\DELL\Downloads\phiblock-keypair.pem" ec2-user@98.84.46.28 "sudo docker exec phiblock_temp-api-1 sed -i 's/\r$//' /app/entrypoint.sh && sudo docker-compose -f ~/phiblock_temp/docker-compose.yml restart"
```

### Problem: Dashboard returns 404

**Cause**: Static file is named `dashboard.html` but needs to be `index.html`.

**Solution**:
```powershell
ssh -i "C:\Users\DELL\Downloads\phiblock-keypair.pem" ec2-user@98.84.46.28 "sudo docker exec phiblock_temp-api-1 mv /app/app/static/dashboard.html /app/app/static/index.html && sudo docker-compose -f ~/phiblock_temp/docker-compose.yml restart api"
```

### Problem: curl package conflicts on Amazon Linux 2023

**Cause**: `curl-minimal` conflicts with `curl`.

**Solution**: Already handled in deploy script - uses `curl-minimal` if curl isn't available.

### Problem: API Key returns "Invalid API Key"

**Solution**:
1. Verify you created a tenant first
2. Verify the customer was created
3. Use the plain key (not the hash)
4. Create a new API key if needed

### Problem: EC2 Public IP Changed

**Cause**: EC2 instances get new IPs when stopped/started.

**Solution**:
1. Attach an Elastic IP in AWS Console
2. Or just use the new IP in the deployment command

---

## Quick Reference

### URLs
- **Swagger Docs**: http://98.84.46.28:8000/docs
- **Dashboard**: http://98.84.46.28:8000/dashboard/
- **Health Check**: http://98.84.46.28:8000/v1/health
- **ReDoc**: http://98.84.46.28:8000/redoc

### Commands
```powershell
# Deploy
.\scripts\push_to_ec2.ps1 -EC2_IP "98.84.46.28" -SSH_KEY_PATH "C:\Users\DELL\Downloads\phiblock-keypair.pem"

# SSH
ssh -i "C:\Users\DELL\Downloads\phiblock-keypair.pem" ec2-user@98.84.46.28

# View logs
ssh -i "C:\Users\DELL\Downloads\phiblock-keypair.pem" ec2-user@98.84.46.28 "cd ~/phiblock_temp && sudo docker-compose logs -f api"

# Restart
ssh -i "C:\Users\DELL\Downloads\phiblock-keypair.pem" ec2-user@98.84.46.28 "cd ~/phiblock_temp && sudo docker-compose restart"
```

---

*Based on deployment session: January 2-7, 2026*
*Last updated: January 7, 2026*
