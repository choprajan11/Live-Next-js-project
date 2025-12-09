# API Documentation

## Authentication

All API endpoints require an API key to be sent in the request headers:

```
X-API-Key: your_api_key_here
```

The API key should be set in your environment variables as `API_KEY`.

## Rate Limiting

The API has rate limiting in place to prevent abuse:
- GET endpoints: 100 requests per minute
- POST /sites endpoint: 50 requests per minute
- POST /sites/{site_id}/deploy endpoint: 10 requests per minute

## Endpoints

### List All Sites
```
GET /api/v1/sites
```

**Response:**
```json
{
    "status": "success",
    "data": {
        "site_id": {
            "domain_name": "example.com",
            "port": 3000,
            "status": "pending",
            "IP_URL": "http://localhost:3000",
            "created_at": "2024-03-20 10:00:00",
            "updated_at": "2024-03-20 10:00:00",
            "domain_status": false,
            "domain_provider": "namecheap",
            "IP_live_status": false,
            "repo": "https://github.com/user/repo",
            "project_dir": "",
            "name": "Example Site"
        }
    }
}
```

### Get Single Site
```
GET /api/v1/sites/{site_id}
```

**Response:**
```json
{
    "status": "success",
    "data": {
        "domain_name": "example.com",
        "port": 3000,
        "status": "pending",
        "IP_URL": "http://localhost:3000",
        "created_at": "2024-03-20 10:00:00",
        "updated_at": "2024-03-20 10:00:00",
        "domain_status": false,
        "domain_provider": "namecheap",
        "IP_live_status": false,
        "repo": "https://github.com/user/repo",
        "project_dir": "",
        "name": "Example Site",
        "id": "site_id"
    }
}
```

### Create New Site
```
POST /api/v1/sites
```

**Request Body:**
```json
{
    "repo": "https://github.com/user/repo",
    "domain": "example.com",
    "name": "Example Site"
}
```

**Response:**
```json
{
    "status": "success",
    "message": "Site created successfully",
    "data": {
        "site_id": "generated_site_id"
    }
}
```

### Deploy Site
```
POST /api/v1/sites/{site_id}/deploy
```

**Response:**
```json
{
    "status": "success",
    "message": "Site deployed successfully"
}
```

## Error Responses

All endpoints return errors in the following format:

```json
{
    "status": "error",
    "message": "Error description"
}
```

Common HTTP status codes:
- 200: Success
- 201: Created successfully
- 400: Bad request (missing or invalid parameters)
- 401: Unauthorized (invalid or missing API key)
- 404: Not found
- 429: Too many requests (rate limit exceeded)
- 500: Server error

## Example Usage (Python)

```python
import requests

API_KEY = "your_api_key_here"
BASE_URL = "http://your-server/api/v1"

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

# List all sites
response = requests.get(f"{BASE_URL}/sites", headers=headers)
sites = response.json()

# Create new site
new_site = {
    "repo": "https://github.com/user/repo",
    "domain": "example.com",
    "name": "Example Site"
}
response = requests.post(f"{BASE_URL}/sites", headers=headers, json=new_site)
site_id = response.json()["data"]["site_id"]

# Deploy site
response = requests.post(f"{BASE_URL}/sites/{site_id}/deploy", headers=headers)
```

## Security Best Practices

1. Always use HTTPS in production
2. Keep your API key secure and never expose it in client-side code
3. Rotate your API key periodically
4. Monitor API usage for suspicious activity
5. Use environment variables for sensitive configuration
