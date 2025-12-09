# Namecheap Domain Setup Guide

This guide explains how to set up your Namecheap domain with our domain management system.

## Prerequisites

1. A Namecheap account with registered domain(s)
2. API access enabled on your Namecheap account
3. Your server's IP address

## Getting API Credentials

1. Log in to your Namecheap account
2. Go to Profile > Tools > API Access
3. Enable API access if not already enabled
4. Note down the following information:
   - API Key
   - API Username (usually same as your Namecheap username)
   - Your whitelisted IP address

## Environment Configuration

Add the following variables to your `.env` file:

```env
NAMECHEAP_API_KEY=your_api_key_here
NAMECHEAP_API_USER=your_username_here
NAMECHEAP_USERNAME=your_namecheap_username
NAMECHEAP_CLIENT_IP=your_whitelisted_ip
NAMECHEAP_API_ENV=production  # or sandbox for testing
```

## Using the Domain Manager

The domain manager will automatically detect whether your domain is managed by Namecheap or Cloudflare and handle it accordingly.

### Basic Usage

```python
from models.add_domain import DomainManager

# Initialize the domain manager
domain_manager = DomainManager()

# Setup your domain
success, logs = domain_manager.setup_domain("yourdomain.com")
print(logs)  # This will show the progress and any necessary instructions

# Add TXT record (for SSL verification)
success, logs = domain_manager.add_txt_record(
    "yourdomain.com",
    "_acme-challenge",
    "verification-token-here"
)
print(logs)
```

## Nameserver Configuration

The system automatically configures your Namecheap domain to use Cloudflare's nameservers:

1. Default Cloudflare nameservers:
   - ns1.cloudflare.com
   - ns2.cloudflare.com

This configuration is mandatory as it allows Cloudflare to manage your domain's DNS records and provide additional features like:
- SSL/TLS encryption
- DDoS protection
- Caching and CDN services
- Web application firewall (WAF)

### Nameserver Propagation

After the nameservers are updated:
1. Wait 24-48 hours for the changes to propagate globally
2. During this time, your domain might experience intermittent DNS resolution
3. Once propagation is complete, all DNS management will be handled through Cloudflare

## DNS Record Management

The system configures DNS records in both Namecheap and Cloudflare during the transition:

1. Root domain (@ or empty hostname)
   - Type: A
   - Points to: Your server IP
   - TTL: 1800 seconds

2. WWW subdomain
   - Type: A
   - Points to: Your server IP
   - TTL: 1800 seconds

3. Wildcard subdomain (*)
   - Type: A
   - Points to: Your server IP
   - TTL: 1800 seconds

Note: Once nameserver propagation is complete, the DNS records in Namecheap will be superseded by Cloudflare's records.

## SSL Certificate Setup

After setting up DNS records:

1. Run the provided certbot command:
   ```bash
   sudo certbot certonly --manual --preferred-challenges dns \
     -d yourdomain.com -d *.yourdomain.com \
     --agree-tos -m your-email@example.com
   ```

2. When certbot asks you to create a TXT record, use the `add_txt_record()` method:
   ```python
   domain_manager.add_txt_record(
       "yourdomain.com",
       "_acme-challenge",
       "verification-token-from-certbot"
   )
   ```

3. Wait for DNS propagation (usually 5-10 minutes)
4. Complete the certbot verification process

## Troubleshooting

### Common Issues

1. **API Authentication Failed**
   - Verify your API credentials in the `.env` file
   - Ensure your IP is whitelisted in Namecheap

2. **DNS Changes Not Visible**
   - DNS changes can take 24-48 hours to propagate fully
   - Use `dig` or `nslookup` to check current DNS records

3. **SSL Certificate Issues**
   - Ensure DNS propagation is complete before verifying with certbot
   - Check that all DNS records are correctly set up

### Getting Help

If you encounter any issues:
1. Check the logs returned by the domain manager methods
2. Verify your Namecheap API access and credentials
3. Ensure your domain is active and properly registered with Namecheap
