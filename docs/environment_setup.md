# Environment Variable Setup

This document describes the environment variables required for the application to run properly.

## Required Environment Variables

### Cloudflare Configuration
- `CLOUDFLARE_API_TOKEN`: Your Cloudflare API token with the necessary permissions
  - Required for domain management and DNS configuration
  - Get it from Cloudflare Dashboard > My Profile > API Tokens

### Server Configuration
- `SERVER_IP`: Your server's public IP address
  - Used for DNS record configuration
  - Example: "123.45.67.89"
- `DEFAULT_PORT`: Default port for Next.js applications (default: 3000)
  - Used when deploying new sites
  - Can be changed if needed

### Application Configuration
- `BASE_DIR`: Base directory for storing site files (default: "local_listing_sites")
  - All deployed sites will be stored in subdirectories here
- `SITES_JSON_PATH`: Path to the sites configuration file (default: "sites.json")
  - Stores metadata about deployed sites

### PM2 Configuration
- `PM2_PREFIX`: Prefix for PM2 process names (default: "nextjs_site_")
  - Helps identify and manage Next.js site processes
  - Example: With prefix "nextjs_site_", a site "example.com" will have PM2 process name "nextjs_site_example.com"

## Setup Instructions

1. Create a new file named `.env` in the root directory of the project
2. Add the following content, replacing the placeholder values with your actual configuration:

```env
# Cloudflare Configuration
CLOUDFLARE_API_TOKEN=your_cloudflare_api_token_here

# Server Configuration
SERVER_IP=your_server_ip_here
DEFAULT_PORT=3000

# Application Configuration
BASE_DIR=local_listing_sites
SITES_JSON_PATH=sites.json

# PM2 Configuration
PM2_PREFIX=nextjs_site_
```

3. Make sure to keep your `.env` file secure and never commit it to version control
4. If you're using version control, add `.env` to your `.gitignore` file

## Notes

- All environment variables have default values, but it's recommended to set them explicitly
- The Cloudflare API token and Server IP are required for proper functionality
- Other variables can use their default values if not specified
- Make sure the BASE_DIR path exists and is writable by the application
