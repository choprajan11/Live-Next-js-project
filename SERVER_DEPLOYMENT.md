# Server Deployment Guide

Deploy the Site Manager Dashboard on your Hetzner VPS.

## Quick Deploy Commands

### 1. SSH into your server
```bash
ssh root@65.109.63.240
```

### 2. Clone the repository
```bash
cd /opt
git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git site-manager
cd site-manager
```

### 3. Install Python dependencies
```bash
# Install pip if not present
apt update && apt install -y python3-pip python3-venv

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install flask flask-socketio flask-login flask-limiter python-dotenv requests
```

### 4. Configure environment
```bash
# Copy and edit the .env file
cp config/env.sample .env
nano .env
```

Update these values in `.env`:
```env
# Server Configuration
SERVER_IP=65.109.63.240
DEFAULT_PORT=3000

# Paths
PROJECT_DEPLOY_PATH=/root/local_listing_sites
SITES_JSON_PATH=sites.json

# Your API credentials (update these!)
CLOUDFLARE_API_TOKEN=your_cloudflare_token
CLOUDFLARE_ACCOUNT_ID=your_account_id
NAMECHEAP_API_KEY=your_namecheap_key
NAMECHEAP_API_USER=your_username
```

### 5. Run with PM2 (Production)
```bash
# Install PM2 if not present
npm install -g pm2

# Start the dashboard
pm2 start "python app.py" --name "site-manager" --interpreter python3

# Save PM2 config
pm2 save
pm2 startup
```

### 6. Access the dashboard
Open in browser: `http://65.109.63.240:5001`

Login: `admin` / `qwety`

---

## Nginx Reverse Proxy (Optional)

To access via domain with SSL:

```nginx
server {
    listen 80;
    server_name manager.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name manager.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/manager.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/manager.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Import Sites from CSV

1. Go to `/bulk-deploy`
2. Click the **CSV** tab
3. Upload your `domain_repository.csv` or paste the content
4. Click **Import CSV**
5. Sites will be added to `sites.json`

---

## Bulk Deploy Sites

After importing:

1. Select **Pending Sites Only** in Deploy Controls
2. Choose parallel workers (3 recommended)
3. Check **Deploy Locally** 
4. Click **Start Bulk Deployment**

Monitor progress in real-time!

---

## File Structure on Server

```
/opt/site-manager/          # Dashboard app
├── app.py
├── sites.json              # Site configurations
├── .env                    # Environment config
└── history/                # Deployment logs

/root/local_listing_sites/  # Deployed Next.js sites
├── example.com/
├── another.com/
└── ...
```

---

## Useful Commands

```bash
# View dashboard logs
pm2 logs site-manager

# Restart dashboard
pm2 restart site-manager

# View all PM2 processes (including deployed sites)
pm2 list

# View specific site logs
pm2 logs nextjs_site_example.com
```

