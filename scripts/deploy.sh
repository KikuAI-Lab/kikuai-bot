#!/bin/bash
# Deployment script for KikuAI Bot
# Usage: ./scripts/deploy.sh [local|production]

set -e

ENV=${1:-local}
SERVER="root@37.27.38.186"
PROJECT_DIR="/root/kikuai-bot"
NGINX_CONF_DIR="/root/kikuai-platform/nginx/conf.d"

echo "🚀 KikuAI Bot Deployment Script"
echo "Environment: $ENV"
echo ""

if [ "$ENV" = "production" ]; then
    echo "📦 Preparing production deployment..."
    
    # Check if .env exists
    if [ ! -f .env ]; then
        echo "❌ .env file not found!"
        exit 1
    fi
    
    # Check required variables
    source .env
    required_vars=("TELEGRAM_BOT_TOKEN" "PADDLE_API_KEY" "PADDLE_WEBHOOK_SECRET")
    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            echo "❌ Required variable $var is not set in .env"
            exit 1
        fi
    done
    
    echo "✅ Environment variables check passed"
    
    # Create deployment package
    echo "📦 Creating deployment package..."
    tar --exclude='.git' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.env' \
        --exclude='*.log' \
        -czf /tmp/kikuai-bot-deploy.tar.gz .
    
    echo "📤 Uploading to server..."
    scp /tmp/kikuai-bot-deploy.tar.gz $SERVER:/tmp/
    
    echo "🔧 Deploying on server..."
    ssh $SERVER << ENDSSH
        set -e
        mkdir -p $PROJECT_DIR
        cd $PROJECT_DIR
        
        # Extract files
        if [ -f /tmp/kikuai-bot-deploy.tar.gz ]; then
            tar -xzf /tmp/kikuai-bot-deploy.tar.gz
            rm /tmp/kikuai-bot-deploy.tar.gz
        fi
ENDSSH
    
    # Upload .env separately after directory is created
    echo "📤 Uploading .env file..."
    scp .env $SERVER:$PROJECT_DIR/.env
    
    echo "🔧 Finalizing deployment..."
    ssh $SERVER << 'ENDSSH'
        set -e
        cd /root/kikuai-bot
        
        # Setup Nginx config
        if [ -f nginx.conf ]; then
            cp nginx.conf /root/kikuai-platform/nginx/conf.d/bot.kikuai.dev.conf
            echo "✅ Nginx config copied"
        fi
        
        # Create Docker network if needed
        if ! docker network ls | grep -q kikuai-platform_public; then
            docker network create kikuai-platform_public
            echo "✅ Docker network created"
        fi
        
        # Deploy with docker-compose
        docker-compose -f docker-compose.prod.yml down || true
        docker-compose -f docker-compose.prod.yml up -d --build
        
        echo "✅ Deployment complete!"
        
        # Show status
        echo ""
        echo "📊 Service Status:"
        docker ps | grep kikuai-bot || echo "No kikuai-bot containers running"
        
        echo ""
        echo "🔍 Health Check:"
        sleep 2
        curl -s http://localhost:8000/healthz || echo "Health check failed"
ENDSSH
    
    echo ""
    echo "✅ Production deployment complete!"
    echo "🔗 Check: https://kikuai.dev/healthz"
    
elif [ "$ENV" = "local" ]; then
    echo "🏠 Starting local development environment..."
    
    # Check if .env exists
    if [ ! -f .env ]; then
        echo "❌ .env file not found!"
        exit 1
    fi
    
    # Start services
    docker-compose down || true
    docker-compose up --build -d
    
    echo ""
    echo "✅ Local environment started!"
    echo "📊 Services:"
    docker-compose ps
    
    echo ""
    echo "📝 Logs:"
    echo "  docker-compose logs -f"
    echo ""
    echo "🧪 Test bot: @kikuai_bot"
    
else
    echo "❌ Unknown environment: $ENV"
    echo "Usage: $0 [local|production]"
    exit 1
fi

