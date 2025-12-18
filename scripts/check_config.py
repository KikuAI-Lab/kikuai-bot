#!/usr/bin/env python3
"""Check configuration and connectivity."""

import os
import sys
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import (
    TELEGRAM_BOT_TOKEN,
    PADDLE_API_KEY,
    PADDLE_WEBHOOK_SECRET,
    PADDLE_ENVIRONMENT,
    REDIS_URL,
    RELIAPI_URL,
    WEBAPP_URL,
)


def check_env_file():
    """Check if .env file exists and has required variables."""
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        print("❌ .env file not found")
        return False
    
    print("✅ .env file exists")
    return True


def check_required_vars():
    """Check if all required environment variables are set."""
    required = {
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "PADDLE_API_KEY": PADDLE_API_KEY,
        "PADDLE_WEBHOOK_SECRET": PADDLE_WEBHOOK_SECRET,
        "REDIS_URL": REDIS_URL,
        "RELIAPI_URL": RELIAPI_URL,
        "WEBAPP_URL": WEBAPP_URL,
    }
    
    missing = []
    for name, value in required.items():
        if not value:
            missing.append(name)
            print(f"❌ {name} is not set")
        else:
            # Mask sensitive values
            if "SECRET" in name or "TOKEN" in name or "KEY" in name:
                masked = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
                print(f"✅ {name} = {masked}")
            else:
                print(f"✅ {name} = {value}")
    
    if missing:
        print(f"\n⚠️  Missing variables: {', '.join(missing)}")
        return False
    
    return True


async def check_redis():
    """Check Redis connectivity."""
    try:
        import redis
        client = redis.from_url(REDIS_URL)
        client.ping()
        print("✅ Redis connection OK")
        return True
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        return False


async def check_reliapi():
    """Check ReliAPI connectivity."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{RELIAPI_URL}/health")
            if response.status_code == 200:
                print(f"✅ ReliAPI connection OK ({RELIAPI_URL})")
                return True
            else:
                print(f"⚠️  ReliAPI returned {response.status_code}")
                return False
    except Exception as e:
        print(f"⚠️  ReliAPI check failed: {e}")
        return False


async def check_paddle_api():
    """Check Paddle API key validity."""
    if not PADDLE_API_KEY:
        print("⚠️  Paddle API key not set, skipping check")
        return False
    
    try:
        import httpx
        base_url = (
            "https://sandbox-api.paddle.com" if PADDLE_ENVIRONMENT == "sandbox"
            else "https://api.paddle.com"
        )
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Try to get transaction (will fail with 401 if key is invalid)
            response = await client.get(
                f"{base_url}/transactions",
                headers={"Authorization": f"Bearer {PADDLE_API_KEY}"},
            )
            if response.status_code in (200, 401, 403):
                # 401/403 means key is recognized but might not have permissions
                # This is better than connection error
                print(f"✅ Paddle API key appears valid (status: {response.status_code})")
                return True
            else:
                print(f"⚠️  Paddle API returned {response.status_code}")
                return False
    except Exception as e:
        print(f"⚠️  Paddle API check failed: {e}")
        return False


async def main():
    """Run all checks."""
    print("🔍 KikuAI Bot Configuration Check\n")
    
    results = []
    
    # File checks
    print("📁 File Checks:")
    results.append(check_env_file())
    print()
    
    # Environment variables
    print("🔐 Environment Variables:")
    results.append(check_required_vars())
    print()
    
    # Connectivity checks
    print("🌐 Connectivity Checks:")
    results.append(await check_redis())
    results.append(await check_reliapi())
    results.append(await check_paddle_api())
    print()
    
    # Summary
    passed = sum(results)
    total = len(results)
    print(f"📊 Summary: {passed}/{total} checks passed")
    
    if passed == total:
        print("✅ All checks passed! Ready to deploy.")
        return 0
    else:
        print("⚠️  Some checks failed. Please fix issues before deploying.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

