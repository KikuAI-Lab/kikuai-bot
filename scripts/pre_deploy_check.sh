#!/bin/bash
# Pre-deployment checklist
# Run this before deploying to production

set -e

echo "🔍 Pre-Deployment Checklist"
echo "============================"
echo ""

ERRORS=0

# Check .env file
echo "1. Checking .env file..."
if [ ! -f .env ]; then
    echo "   ❌ .env file not found"
    ERRORS=$((ERRORS + 1))
else
    echo "   ✅ .env file exists"
    
    # Check required variables
    source .env
    required_vars=(
        "TELEGRAM_BOT_TOKEN"
        "PADDLE_API_KEY"
        "PADDLE_WEBHOOK_SECRET"
        "REDIS_URL"
        "RELIAPI_URL"
        "WEBAPP_URL"
    )
    
    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            echo "   ❌ $var is not set"
            ERRORS=$((ERRORS + 1))
        else
            echo "   ✅ $var is set"
        fi
    done
fi

echo ""

# Check Docker files
echo "2. Checking Docker configuration..."
if [ ! -f Dockerfile ]; then
    echo "   ❌ Dockerfile not found"
    ERRORS=$((ERRORS + 1))
else
    echo "   ✅ Dockerfile exists"
fi

if [ ! -f docker-compose.yml ]; then
    echo "   ❌ docker-compose.yml not found"
    ERRORS=$((ERRORS + 1))
else
    echo "   ✅ docker-compose.yml exists"
fi

if [ ! -f docker-compose.prod.yml ]; then
    echo "   ❌ docker-compose.prod.yml not found"
    ERRORS=$((ERRORS + 1))
else
    echo "   ✅ docker-compose.prod.yml exists"
fi

echo ""

# Check Nginx config
echo "3. Checking Nginx configuration..."
if [ ! -f nginx.conf ]; then
    echo "   ❌ nginx.conf not found"
    ERRORS=$((ERRORS + 1))
else
    echo "   ✅ nginx.conf exists"
fi

echo ""

# Check Python files
echo "4. Checking Python files..."
if [ ! -f bot/main.py ]; then
    echo "   ❌ bot/main.py not found"
    ERRORS=$((ERRORS + 1))
else
    echo "   ✅ bot/main.py exists"
fi

if [ ! -f api/main.py ]; then
    echo "   ❌ api/main.py not found"
    ERRORS=$((ERRORS + 1))
else
    echo "   ✅ api/main.py exists"
fi

echo ""

# Check requirements
echo "5. Checking requirements.txt..."
if [ ! -f requirements.txt ]; then
    echo "   ❌ requirements.txt not found"
    ERRORS=$((ERRORS + 1))
else
    echo "   ✅ requirements.txt exists"
fi

echo ""

# Summary
echo "============================"
if [ $ERRORS -eq 0 ]; then
    echo "✅ All checks passed! Ready to deploy."
    exit 0
else
    echo "❌ Found $ERRORS error(s). Please fix before deploying."
    exit 1
fi










