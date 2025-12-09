##################################### Complete Process #################



pm2 start npm --name "assurewaste" -- run start -- -p 3003

pm2 save



#################### Nginx Process #####################


sudo nano /etc/nginx/sites-available/ allinrentadumpster.com

server {
    listen 80;
    server_name allinrentadumpster.com www.allinrentadumpster.com;

    location / {
        proxy_pass http://127.0.0.1:3004;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}

sudo ln -s /etc/nginx/sites-available/allinrentadumpster.com /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx




# Request wildcard cert: will prompt you with the TXT value to add
sudo certbot certonly --manual --preferred-challenges dns \
  -d assurewaste.com -d '*.assurewaste.com' \
  --agree-tos -m you@your-email.com



save give value from "udo certbot certonly...." command in cloundflare 'Type = TXT, Name = _acme-challenge
value = "give from sudo certbot command "



######### Edit Nginx file again 

sudo nano /etc/nginx/sites-available/allinrentadumpster.com 


map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

# Redirect all HTTP traffic to HTTPS
server {
    listen 80;
    server_name junkhaulingriverside.com www.junkhaulingriverside.com *.junkhaulingriverside.com;
    return 301 https://$host$request_uri;
}

# Main HTTPS server block
server {
    listen 443 ssl http2;
    server_name junkhaulingriverside.com www.junkhaulingriverside.com *.junkhaulingriverside.com;

    ssl_certificate     /etc/letsencrypt/live/junkhaulingriverside.com-0001/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/junkhaulingriverside.com-0001/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;

    # Redirect www -> non-www
    if ($host = www.junkhaulingriverside.com) {
        return 301 https://junkhaulingriverside.com$request_uri;
    }

    # Proxy Next.js static assets
    location /_next/ {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Proxy main Next.js app
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
    }
}


sudo nginx -t
sudo systemctl reload nginx
