# PhiBlock Complete Setup Guide

A comprehensive, step-by-step guide to set up and run PhiBlock from scratch.

> **Target Audience**: Developers familiar with programming basics but new to this specific stack (FastAPI, Docker, PostgreSQL, Redis, Celery).

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Clone the Repository](#2-clone-the-repository)
3. [Get External API Keys](#3-get-external-api-keys)
4. [Configure Environment Variables](#4-configure-environment-variables)
5. [Local Development Setup (Without Docker)](#5-local-development-setup-without-docker)
6. [Docker Setup (Recommended)](#6-docker-setup-recommended)
7. [Database Migrations](#7-database-migrations)
8. [Create Your First Tenant and API Key](#8-create-your-first-tenant-and-api-key)
9. [Test the API](#9-test-the-api)
10. [Access the Dashboard](#10-access-the-dashboard)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Prerequisites

### 1.1 Required Software

Before you begin, ensure you have the following installed:

#### Step 1.1.1: Install Python 3.12+
1. Go to https://www.python.org/downloads/
2. Download Python 3.12 or later
3. Run the installer
4. **IMPORTANT**: Check "Add Python to PATH" during installation
5. Verify installation:
   ```bash
   python --version
   ```
   Expected output: `Python 3.12.x`

#### Step 1.1.2: Install Git
1. Go to https://git-scm.com/downloads
2. Download and install for your OS
3. Verify installation:
   ```bash
   git --version
   ```

#### Step 1.1.3: Install Docker Desktop
1. Go to https://www.docker.com/products/docker-desktop/
2. Download Docker Desktop for your OS
3. Run the installer and follow prompts
4. Start Docker Desktop
5. Verify installation:
   ```bash
   docker --version
   docker-compose --version
   ```

#### Step 1.1.4: Install a Code Editor (Optional)
- Recommended: [VS Code](https://code.visualstudio.com/)
- Install the Python extension for VS Code

---

## 2. Clone the Repository

### Step 2.1: Open Terminal
- **Windows**: Open PowerShell or Command Prompt
- **Mac/Linux**: Open Terminal

### Step 2.2: Navigate to Your Projects Folder
```bash
cd ~/Desktop/projects
# or wherever you want to store the project
```

### Step 2.3: Clone the Repository
```bash
git clone <your-repo-url> PhiBlock
cd PhiBlock
```

### Step 2.4: Verify Project Structure
```bash
ls
```
You should see:
- `app/` - Main application code
- `workers/` - Celery worker tasks
- `alembic/` - Database migrations
- `docker-compose.yml` - Docker configuration
- `Dockerfile` - Container build instructions
- `.env.example` - Environment template
- `requirements.txt` - Python dependencies

---

## 3. Get External API Keys

PhiBlock integrates with several external services. Some are **required**, others are **optional**.

### 3.1 Stripe (Optional - For Billing)

Stripe enables usage-based billing for your API.

#### Step 3.1.1: Create a Stripe Account
1. Go to https://dashboard.stripe.com/register
2. Fill in your email and create a password
3. Click "Create account"
4. Verify your email address

#### Step 3.1.2: Get Your Secret Key
1. Log in to https://dashboard.stripe.com
2. Look at the top-right: ensure "Test mode" toggle is ON (orange)
3. Click "Developers" in the left sidebar
4. Click "API keys"
5. Under "Standard keys", find "Secret key"
6. Click "Reveal test key"
7. Copy the key (starts with `sk_test_`)
8. **Save this key** - you'll need it for `.env`

#### Step 3.1.3: Create a Price ID (For Metered Billing)
1. In Stripe Dashboard, go to "Products" in the left sidebar
2. Click "+ Add product"
3. Name: "PhiBlock API Usage"
4. Pricing model: Select "Recurring"
5. Click "More pricing options"
6. Select "Usage-based"
7. Unit label: "tokens"
8. Price per unit: $0.0001 (or your desired rate)
9. Click "Save product"
10. On the product page, find the price and click it
11. Copy the Price ID (starts with `price_`)
12. **Save this ID** - you'll need it for `.env`

---

### 3.2 Sentry (Optional - For Error Monitoring)

Sentry helps track errors and performance issues in production.

#### Step 3.2.1: Create a Sentry Account
1. Go to https://sentry.io/signup/
2. Sign up with email, Google, or GitHub
3. Complete the signup process

#### Step 3.2.2: Create a New Project
1. After signup, click "Create Project"
2. Platform: Select "Python"
3. Set your alert frequency preferences
4. Project name: "phiblock" (or your preferred name)
5. Click "Create Project"

#### Step 3.2.3: Get Your DSN
1. After project creation, you'll see setup instructions
2. Look for the DSN - it looks like:
   ```
   https://abc123@o456789.ingest.sentry.io/1234567
   ```
3. Copy this entire URL
4. **Save this DSN** - you'll need it for `.env`

#### Step 3.2.4: Alternative - Find DSN Later
1. Go to Settings → Projects → [Your Project]
2. Click "Client Keys (DSN)" in the left sidebar
3. Copy the DSN

---

### 3.3 HuggingFace (Optional - For ML Models)

HuggingFace provides access to machine learning models for advanced detection.

#### Step 3.3.1: Create a HuggingFace Account
1. Go to https://huggingface.co/join
2. Fill in username, email, and password
3. Click "Create Account"
4. Verify your email

#### Step 3.3.2: Create an Access Token
1. Log in to https://huggingface.co
2. Click your profile picture (top-right)
3. Click "Settings"
4. Click "Access Tokens" in the left sidebar
5. Click "New token"
6. Name: "phiblock-api"
7. Type: Select "Read"
8. Click "Generate a token"
9. Copy the token (starts with `hf_`)
10. **Save this token** - you'll need it for `.env`

---

## 4. Configure Environment Variables

### Step 4.1: Create Your .env File
```bash
cp .env.example .env
```

### Step 4.2: Open .env in Your Editor
```bash
code .env
# or use any text editor:
# notepad .env  (Windows)
# nano .env     (Mac/Linux)
```

### Step 4.3: Configure Each Variable

Below is every variable in `.env.example` with explanations:

---

#### 4.3.1 Core API Configuration

```env
DEBUG=false
```
- **What it does**: Enables debug mode with verbose logging
- **For development**: Set to `true`
- **For production**: Set to `false`

```env
LOG_LEVEL=INFO
```
- **Options**: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- **Recommended**: `INFO` for production, `DEBUG` for development

```env
# CORS_ALLOWED_ORIGINS=https://app.yourdomain.com
```
- **What it does**: Restricts which domains can call your API
- **For development**: Leave commented out (allows all)
- **For production**: Uncomment and set your frontend domains

---

#### 4.3.2 Database Configuration

```env
DATABASE_URL=postgresql://user:password@localhost:5432/phiblock
```
- **For Docker setup**: Use `postgresql://user:password@db:5432/phiblock`
  - `db` refers to the Docker container name
- **For local setup**: Use `postgresql://user:password@localhost:5432/phiblock`
- **Format**: `postgresql://USERNAME:PASSWORD@HOST:PORT/DATABASE_NAME`

**Change the default credentials for production!**

```env
SQL_ECHO=false
```
- **What it does**: Logs all SQL queries
- Set to `true` for debugging database issues

---

#### 4.3.3 Redis Configuration

```env
REDIS_URL=redis://localhost:6379/0
```
- **For Docker setup**: Use `redis://redis:6379/0`
- **For local setup**: Use `redis://localhost:6379/0`
- Redis is required for caching, rate limiting, and Celery

---

#### 4.3.4 Caching Configuration

```env
CACHE_ENABLED=true
CACHE_TTL=300
```
- `CACHE_ENABLED`: Enable/disable response caching
- `CACHE_TTL`: Cache lifetime in seconds (300 = 5 minutes)

---

#### 4.3.5 Security & Encryption

```env
SECRET_KEY=your-secret-key-here-change-in-production
```
- **CRITICAL**: Change this to a random string in production!
- Generate a secure key:
  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```
- Copy the output and paste it as your SECRET_KEY

```env
API_KEY_SALT=your-api-key-salt-here
```
- Used for hashing API keys
- Generate another random string:
  ```bash
  python -c "import secrets; print(secrets.token_hex(16))"
  ```

```env
AUDIT_ENCRYPTION_SECRET=your-audit-secret-key-32-chars-at-least
```
- Used for encrypting audit logs
- Must be at least 32 characters
- Generate:
  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```

```env
PII_ENCRYPTION_KEY=your-fernet-key-or-passphrase
```
- Used for encrypting PII in the database
- Can be a passphrase or a Fernet key
- Generate:
  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```

```env
PII_REDACTION_KEY=your-redaction-hmac-key
```
- Used for consistent hash-based redaction
- Generate:
  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```

---

#### 4.3.6 Celery & Workers

```env
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```
- **For Docker**: Change `localhost` to `redis`
- These should match your `REDIS_URL`

---

#### 4.3.7 Stripe Billing (Optional)

```env
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PRICE_ID=price_...
```
- Paste the keys you got from [Section 3.1](#31-stripe-optional---for-billing)
- Leave as-is if not using Stripe

---

#### 4.3.8 Webhook Security (Optional)

```env
WEBHOOK_SIGNING_SECRET=your-webhook-secret
ALLOWED_WEBHOOK_DOMAINS=yourdomain.com,partner.com
WEBHOOK_RATE_LIMIT_PER_MINUTE=60
WEBHOOK_SIGNATURE_WINDOW=300
```
- Only needed if using webhooks
- `WEBHOOK_SIGNING_SECRET`: Secret for signing webhook payloads
- `ALLOWED_WEBHOOK_DOMAINS`: Comma-separated list of allowed domains
- Leave defaults if not using webhooks

---

#### 4.3.9 Monitoring & External Services

```env
SENTRY_DSN=
```
- Paste your Sentry DSN from [Section 3.2](#32-sentry-optional---for-error-monitoring)
- Leave empty if not using Sentry

```env
# HUGGINGFACE_TOKEN=your-hf-token
```
- Uncomment and paste your token from [Section 3.3](#33-huggingface-optional---for-ml-models)
- Only needed for private models

---

#### 4.3.10 AWS Secrets Manager (Optional)

```env
# USE_AWS_SECRETS=false
# AWS_REGION=us-east-1
```
- Advanced feature for production
- Leave commented out for development

---

### Step 4.4: Save Your .env File

After filling in all values, save and close the file.

### Step 4.5: Verify .env is Ignored by Git

Check that `.env` is in `.gitignore`:
```bash
cat .gitignore | grep "\.env"
```
You should see `.env` listed. **Never commit your .env file!**

---

## 5. Local Development Setup (Without Docker)

If you prefer to run without Docker, follow these steps.

### Step 5.1: Create a Virtual Environment
```bash
python -m venv venv
```

### Step 5.2: Activate the Virtual Environment

**Windows (PowerShell):**
```powershell
.\venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```cmd
.\venv\Scripts\activate.bat
```

**Mac/Linux:**
```bash
source venv/bin/activate
```

### Step 5.3: Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 5.4: Download spaCy Model
```bash
python -m spacy download en_core_web_sm
```

### Step 5.5: Install PostgreSQL Locally
1. Download from https://www.postgresql.org/download/
2. Install and remember the password you set
3. Create the database:
   ```bash
   createdb phiblock
   ```

### Step 5.6: Install Redis Locally
**Windows:**
1. Download from https://github.com/microsoftarchive/redis/releases
2. Extract and run `redis-server.exe`

**Mac:**
```bash
brew install redis
brew services start redis
```

**Linux:**
```bash
sudo apt install redis-server
sudo systemctl start redis
```

### Step 5.7: Run Database Migrations
```bash
alembic upgrade head
```

### Step 5.8: Start the API Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Step 5.9: Start the Celery Worker (New Terminal)
Open a new terminal, activate the virtual environment, then:
```bash
celery -A workers.celery_app worker --loglevel=info
```

---

## 6. Docker Setup (Recommended)

Docker is the easiest way to run PhiBlock with all dependencies.

### Step 6.1: Ensure Docker Desktop is Running
- Open Docker Desktop
- Wait until the status shows "Docker is running"

### Step 6.2: Update .env for Docker

Edit your `.env` file to use Docker container names:
```env
DATABASE_URL=postgresql://user:password@db:5432/phiblock
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
```

### Step 6.3: Build and Start Containers
```bash
docker-compose up -d --build
```

This command:
- Builds the Docker image from `Dockerfile`
- Starts 4 containers: `api`, `worker`, `db` (PostgreSQL), `redis`
- Runs in detached mode (`-d`) so you get your terminal back

### Step 6.4: Check Container Status
```bash
docker-compose ps
```
All containers should show "Up".

### Step 6.5: View Logs
```bash
# All containers
docker-compose logs -f

# Specific container
docker-compose logs -f api
```

### Step 6.6: Stop Containers
```bash
docker-compose down
```

### Step 6.7: Stop and Remove Data
```bash
docker-compose down -v
```
**Warning**: This deletes all database data!

---

## 7. Database Migrations

Migrations are run automatically when using Docker (via `entrypoint.sh`).

For manual migrations:

### Step 7.1: Create a New Migration
```bash
alembic revision --autogenerate -m "description of change"
```

### Step 7.2: Apply Migrations
```bash
alembic upgrade head
```

### Step 7.3: View Migration History
```bash
alembic history
```

---

## 8. Create Your First Tenant and API Key

PhiBlock uses a multi-tenant architecture. You need to create:
1. A **Tenant** (organization/company)
2. A **Customer** (user within the tenant)
3. An **API Key** (for authentication)

### Step 8.1: Access the API

Open your browser to: http://localhost:8000/docs

This is the Swagger UI for testing endpoints.

### Step 8.2: Create a Tenant

**Using curl:**
```bash
curl -X POST "http://localhost:8000/v1/tenants" \
  -H "Content-Type: application/json" \
  -d '{"name": "My Company", "plan": "pro"}'
```

**Using Swagger UI:**
1. Go to http://localhost:8000/docs
2. Find `POST /v1/tenants`
3. Click "Try it out"
4. Enter:
   ```json
   {
     "name": "My Company",
     "plan": "pro"
   }
   ```
5. Click "Execute"
6. Note the `id` in the response - this is your `tenant_id`

### Step 8.3: Create a Customer and API Key

Since there's no dedicated API endpoint for creating API keys, use this script.

**For Docker:**
```bash
docker exec -it phiblock_temp-api-1 python -c "
from app.database import SessionLocal
from app.models import Tenant, Customer, APIKey
import hashlib
import secrets

db = SessionLocal()

# Get the tenant you created
tenant = db.query(Tenant).first()
if not tenant:
    print('ERROR: Create a tenant first!')
    exit(1)

print(f'Using tenant: {tenant.name} (ID: {tenant.id})')

# Create customer if not exists
customer = db.query(Customer).filter(Customer.tenant_id == tenant.id).first()
if not customer:
    customer = Customer(
        name='Admin User',
        email='admin@example.com',
        tenant_id=tenant.id
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    print(f'Created customer: {customer.name}')

# Create API key
plain_key = secrets.token_hex(16)
hashed_key = hashlib.sha256(plain_key.encode()).hexdigest()
api_key = APIKey(
    customer_id=customer.id,
    tenant_id=tenant.id,
    key_hash=hashed_key,
    name='My API Key'
)
db.add(api_key)
db.commit()

print(f'')
print(f'YOUR API KEY: {plain_key}')
print(f'')
print('Save this key! It cannot be retrieved later.')
db.close()
"
```

**Save the API key** - you'll use it for all API calls!

---

## 9. Test the API

### Step 9.1: Health Check (No Auth Required)
```bash
curl http://localhost:8000/v1/health
```
Expected: `{"status":"healthy","version":"0.1.0"}`

### Step 9.2: Analyze a Prompt (Auth Required)
```bash
curl -X POST "http://localhost:8000/v1/analyze" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY_HERE" \
  -d '{"prompt": "My email is john@example.com and my SSN is 123-45-6789"}'
```

Expected response (PII detected):
```json
{
  "request_id": "...",
  "status": "completed",
  "sanitized_prompt": "My email is [EMAIL] and my SSN is [SSN]",
  "detections": {
    "pii_found": true,
    "entities": [...],
    "injection_detected": false,
    "injection_score": 0.0
  }
}
```

### Step 9.3: Test Analytics (Auth Required)
```bash
curl "http://localhost:8000/v1/analytics/stats?range=7d" \
  -H "X-API-Key: YOUR_API_KEY_HERE"
```

---

## 10. Access the Dashboard

### Step 10.1: Open the Dashboard
Navigate to: http://localhost:8000/dashboard/

### Step 10.2: Enter Your API Key
1. You'll see a modal asking for your API key
2. Paste the API key you created in Step 8.3
3. Click "Access Dashboard"

### Step 10.3: Explore the Dashboard
- **Total Requests**: Number of API calls
- **Estimated Cost**: Token usage costs
- **Attacks Blocked**: Injection attempts detected
- **Avg Latency**: Response time

---

## 11. Troubleshooting

### Problem: "Connection refused" to database
**Solution**: Ensure PostgreSQL is running
```bash
# Docker
docker-compose ps

# Local
sudo systemctl status postgresql
```

### Problem: "Connection refused" to Redis
**Solution**: Ensure Redis is running
```bash
# Docker
docker-compose ps

# Local
redis-cli ping
```

### Problem: API Key returns "Invalid API Key"
**Solution**:
1. Verify the key was created correctly
2. Check the key isn't revoked
3. Ensure you're using the plain key, not the hash

### Problem: Docker build fails
**Solution**:
```bash
# Clear Docker cache
docker system prune -af
docker-compose build --no-cache
```

### Problem: Permission denied for entrypoint.sh
**Solution**: Line ending issue (Windows CRLF vs Unix LF)
```bash
# Inside container
sed -i 's/\r$//' entrypoint.sh
chmod +x entrypoint.sh
```

### Problem: Dashboard shows 404
**Solution**: The dashboard file must be named `index.html`
```bash
mv app/static/dashboard.html app/static/index.html
```

---

## Next Steps

- Read the API documentation at `/docs`
- Set up Stripe for billing
- Configure Sentry for error monitoring
- Deploy to production (see AWS_DEPLOYMENT_GUIDE.md)

---

*Last updated: January 7, 2026*
