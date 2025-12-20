# Quickstart: KikuAI Masker

Masker allows you to anonymously redact PII and sensitive data from text via a simple API.

## 1. Get your API Key
Log in to the [KikuAI Dashboard](https://kikuai.dev/webapp/dashboard.html) via Telegram and create a new API key with the `masker` scope.

Your key will follow the format: `kikuai_{prefix}_{secret}`.

## 2. Your First Request

### Curl
```bash
curl -X POST "https://api.kikuai.dev/v1/masker" \
     -H "X-API-Key: YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"text": "My email is john.doe@example.com and my phone is +1-202-555-0123"}'
```

### Python (requests)
```python
import requests

url = "https://api.kikuai.dev/v1/masker"
headers = {
    "X-API-Key": "YOUR_API_KEY",
    "Content-Type": "application/json"
}
payload = {
    "text": "My email is john.doe@example.com"
}

response = requests.post(url, headers=headers, json=payload)
print(response.json())
# Output: {"masked_text": "My email is [EMAIL]", "request_id": "..."}
```

### Node.js (fetch)
```javascript
const response = await fetch("https://api.kikuai.dev/v1/masker", {
  method: "POST",
  headers: {
    "X-API-Key": "YOUR_API_KEY",
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    text: "My email is john.doe@example.com"
  })
});

const data = await response.json();
console.log(data);
```

## Response Headers
Every response includes professional tracing headers:
- `X-Request-ID`: A unique identifier for the request. Always provide this when contacting support.

## Error Codes
| Code | Description |
|------|-------------|
| `401` | Invalid or inactive API key. |
| `402` | **Payment Required**. Your prepaid balance is $0. Please top up via @kikuai_bot. |
| `429` | **Too Many Requests**. Rate limit exceeded or too many auth failures. |
| `500` | Internal server error. |
