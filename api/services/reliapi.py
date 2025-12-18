"""ReliAPI integration service."""

import httpx
from typing import Dict, Any, Optional
from config.settings import RELIAPI_URL


class ReliAPIService:
    """Service for interacting with ReliAPI."""
    
    def __init__(self):
        self.base_url = RELIAPI_URL
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def proxy_llm_request(
        self,
        api_key: str,
        request_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Proxy LLM request to ReliAPI."""
        url = f"{self.base_url}/proxy/llm"
        headers = {
            "X-RapidAPI-Key": api_key,  # ReliAPI uses RapidAPI key format
            "Content-Type": "application/json",
        }
        
        try:
            response = await self.client.post(url, json=request_data, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise Exception(f"ReliAPI error: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            raise Exception(f"Request error: {str(e)}")
    
    async def proxy_http_request(
        self,
        api_key: str,
        request_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Proxy HTTP request to ReliAPI."""
        url = f"{self.base_url}/proxy/http"
        headers = {
            "X-RapidAPI-Key": api_key,
            "Content-Type": "application/json",
        }
        
        try:
            response = await self.client.post(url, json=request_data, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise Exception(f"ReliAPI error: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            raise Exception(f"Request error: {str(e)}")
    
    async def health_check(self) -> bool:
        """Check if ReliAPI is healthy."""
        try:
            response = await self.client.get(f"{self.base_url}/healthz", timeout=5.0)
            return response.status_code == 200
        except:
            return False
    
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

