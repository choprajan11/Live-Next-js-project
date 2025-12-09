import os
import json
from datetime import datetime
import uuid
import requests
import subprocess
import xml.etree.ElementTree as ET
from urllib.parse import urlencode
from typing import Tuple, List, Optional, Dict
import time
import re
import threading

# Global lock for certbot to prevent concurrent runs
certbot_lock = threading.Lock()

def validate_domain_name(domain_name: str) -> bool:
    """
    Validate domain name format.
    Returns True if valid, False otherwise.
    """
    # Basic domain name validation regex
    pattern = r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
    return bool(re.match(pattern, domain_name))

class NamecheapClient:
    def __init__(self):
        # Default values for development/testing
        self.api_key = os.getenv('NAMECHEAP_API_KEY', 'e8ba57c4e9d848c4b8fe08f56f7ec8cc')
        self.api_user = os.getenv('NAMECHEAP_API_USER', 'Kingsgrimbyte')
        self.username = os.getenv('NAMECHEAP_USERNAME', 'Kingsgrimbyte')
        self.api_env = os.getenv('NAMECHEAP_API_ENV', 'production')
        self.base_url = 'https://api.namecheap.com/xml.response'
        
        # Get public IP if not provided
        self.client_ip = os.getenv('NAMECHEAP_CLIENT_IP')
        if not self.client_ip:
            self.client_ip = self._get_public_ip()
        
        # Log environment setup
        print("Namecheap Client initialized with:")
        print(f"API User: {self.api_user}")
        print(f"Username: {self.username}")
        print(f"Client IP: {self.client_ip}")
        print(f"API Environment: {self.api_env}")
        
        print("\nIMPORTANT: Ensure your IP is whitelisted in Namecheap:")
        print(f"Current IP: {self.client_ip}")
        print("Go to: Namecheap → Profile → Tools → Namecheap API Access → Edit Whitelisted IPs")
        
    def _get_public_ip(self) -> str:
        """Get public IP address using multiple fallback services"""
        services = [
            "https://api.ipify.org?format=json",
            "https://ifconfig.me/all.json",
            "https://ipinfo.io/json"
        ]
        for service in services:
            try:
                response = requests.get(service, timeout=6)
                response.raise_for_status()
                data = response.json()
                # Try different possible key names
                for key in ("ip", "ip_addr", "ip_address"):
                    if key in data:
                        return data[key]
                # Try direct text response
                text = response.text.strip()
                if text and all(c.isdigit() or c == '.' for c in text):
                    return text
            except Exception as e:
                print(f"Warning: Failed to get IP from {service}: {str(e)}")
                continue
        raise RuntimeError("Unable to determine public IP. Check network connection.")

    def _make_request(self, command: str, params: dict = None, max_retries: int = 3) -> ET.Element:
        """
        Make a request to Namecheap API with retry mechanism and enhanced error handling
        
        Args:
            command: API command to execute
            params: Additional parameters for the request
            max_retries: Maximum number of retry attempts
            
        Returns:
            ET.Element: Parsed XML response
            
        Raises:
            ValueError: If required parameters are missing
            requests.exceptions.RequestException: If the request fails after all retries
            ET.ParseError: If the response XML is invalid
            Exception: For other API-related errors
        """
        if params is None:
            params = {}
            
        # Add required parameters exactly like in name_cheap.py
        base_params = {
            "ApiUser": self.api_user,
            "ApiKey": self.api_key,
            "UserName": self.username,
            "ClientIp": self.client_ip,
            "Command": command
        }
        params.update(base_params)
        
        # Validate required parameters
        for key, value in base_params.items():
            if not value:
                raise ValueError(f"Required parameter {key} is missing")
        
        # Implement retry mechanism
        last_exception = None
        for attempt in range(max_retries):
            try:
                response = requests.get(self.base_url, params=params, timeout=30)
                print(f"Namecheap API Response: {response.text}")  # Log response for debugging
                
                if response.ok:
                    root = ET.fromstring(response.content)
                    status = root.attrib.get('Status')
                    if status == 'OK':
                        return root
                    else:
                        errors = root.findall('.//Errors/Error')
                        error_msg = '; '.join([error.text for error in errors])
                        raise Exception(f"Namecheap API error: {error_msg}")
                        
            except requests.exceptions.RequestException as e:
                last_exception = e
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2  # Exponential backoff
                    time.sleep(wait_time)
                continue
                
        # If we get here, all retries failed
        raise last_exception or Exception("Request failed after all retries")

    def set_nameservers(self, domain_name: str, nameservers: List[str]) -> bool:
        """Set custom nameservers for a domain"""
        try:
            # Get fresh client IP right before making the request
            client_ip = self._get_public_ip()
            print(f"\nUsing client IP: {client_ip}")
            
            # Split domain into SLD and TLD
            sld, tld = domain_name.split('.', 1)
            
            # Build parameters exactly like in name_cheap.py
            params = {
                "ApiUser": self.api_user,
                "ApiKey": self.api_key,
                "UserName": self.username,
                "ClientIp": client_ip,  # Use fresh IP
                "Command": "namecheap.domains.dns.setCustom",
                "SLD": sld,
                "TLD": tld,
                "NameServers": ','.join(nameservers)
            }
            
            # Debug output (hiding API key)
            safe_params = params.copy()
            safe_params["ApiKey"] = "*****REDACTED*****"
            print("\n[DEBUG] Request URL (API key hidden):")
            print(self.base_url + "?" + urlencode(safe_params))
            
            # Make request exactly like in name_cheap.py
            response = requests.get(self.base_url, params=params, timeout=15)
            
            # Print raw response for debugging
            print("\n---- API RESPONSE ----")
            print(response.text)
            print("---- End response ----\n")
            
            # Check if response is successful
            response.raise_for_status()
            
            # Parse response
            root = ET.fromstring(response.content)
            
            # Define namespace
            ns = {'nc': 'http://api.namecheap.com/xml.response'}
            
            status = root.attrib.get('Status')
            print(f"Response Status: {status}")
            
            if status == 'OK':
                # Use proper namespace in XPath
                result = root.find('.//nc:DomainDNSSetCustomResult', namespaces=ns)
                if result is not None:
                    updated = result.attrib.get('Updated', '').lower() == 'true'
                    domain = result.attrib.get('Domain', '')
                    if updated:
                        print(f"✅ Successfully updated nameservers for {domain}")
                        return True
                    else:
                        print(f"❌ Failed to update nameservers for {domain}")
                        return False
                else:
                    print("❌ Could not find DomainDNSSetCustomResult in response")
                    print("Response structure:", ET.tostring(root, encoding='unicode'))
                    return False
            
            # Handle errors
            errors = root.findall('.//nc:Errors/nc:Error', namespaces=ns)
            if errors:
                error_msg = '; '.join([error.text for error in errors if error.text])
                print(f"❌ Namecheap API error: {error_msg}")
                if any(ip_msg in error_msg.lower() for ip_msg in ["ip is not whitelisted", "ip is not in whitelist", "unauthorized"]):
                    print(f"\nIMPORTANT: Your IP ({client_ip}) must be whitelisted in Namecheap!")
                    print("Go to: Namecheap → Profile → Tools → Namecheap API Access → Edit Whitelisted IPs")
            elif status != 'OK':
                print("❌ API request failed with non-OK status")
            else:
                print("❌ API request completed but response structure was unexpected")
                print("Response structure:", ET.tostring(root, encoding='unicode'))
            return False
            
        except requests.HTTPError as e:
            print(f"❌ HTTP error: {e}")
            print(f"Response text: {getattr(e.response, 'text', '')}")
            return False
        except ET.ParseError as e:
            print(f"❌ XML parsing error: {e}")
            print("Raw response:", response.text if 'response' in locals() else 'No response')
            return False
        except Exception as e:
            print(f"❌ Error setting nameservers: {str(e)}")
            if 'response' in locals():
                print(f"Response content: {response.text}")
            return False

    def get_current_nameservers(self, domain_name: str) -> List[str]:
        """Get current nameservers for a domain"""
        sld, tld = domain_name.split('.', 1)
        
        try:
            response = self._make_request('namecheap.domains.getinfo', {
                'SLD': sld,
                'TLD': tld
            })
            
            ns_elements = response.findall('.//DomainDNSGetHostsResult/host[@Type="NS"]')
            return [ns.attrib.get('Address') for ns in ns_elements if ns.attrib.get('Address')]
        except Exception as e:
            print(f"Error getting nameservers: {str(e)}")
            return []

class CloudflareClient:
    def __init__(self):
        # Default values for development/testing
        self.api_token = os.getenv('CLOUDFLARE_API_TOKEN', '5Cky6x43POBEyloqJhgdCGT37jtVImhneiDup0no')
        self.account_id = os.getenv('CLOUDFLARE_ACCOUNT_ID', 'cde8c95ccae7ecdcd32ae3d98b61f45a')
        self.base_url = "https://api.cloudflare.com/client/v4"
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }
        
        # Log environment setup
        print("Cloudflare Client initialized with:")
        print(f"Account ID: {self.account_id}")
        print(f"API URL: {self.base_url}")
        
    def _log_api_response(self, response: requests.Response, operation: str) -> None:
        """Log API response details for debugging"""
        try:
            data = response.json()
            success = data.get('success', False)
            errors = data.get('errors', [])
            messages = data.get('messages', [])
            
            if not success:
                error_msgs = [f"- {error.get('message', 'Unknown error')}" for error in errors]
                print(f"❌ Cloudflare API error in {operation}:")
                print("\n".join(error_msgs))
            
            if messages:
                print(f"ℹ️ Cloudflare API messages for {operation}:")
                for msg in messages:
                    print(f"- {msg}")
                    
        except Exception as e:
            print(f"❌ Error parsing Cloudflare API response: {str(e)}")

    def create_zone(self, domain_name: str) -> Optional[str]:
        """Create a new zone in Cloudflare"""
        url = f"{self.base_url}/zones"
        payload = {
            "name": domain_name,
            "account": {"id": self.account_id},
            "jump_start": True
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)
            self._log_api_response(response, f"create_zone({domain_name})")
            
            if response.ok:
                data = response.json()
                if data.get('success'):
                    return data['result']['id']
            return None
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to create Cloudflare zone: {str(e)}")
            return None

    def get_zone(self, domain_name: str) -> Optional[str]:
        """Get zone ID for a domain"""
        url = f"{self.base_url}/zones"
        params = {"name": domain_name}
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            self._log_api_response(response, f"get_zone({domain_name})")
            
            if response.ok:
                data = response.json()
                if data.get('success'):
                    zones = data['result']
                    return zones[0]['id'] if zones else None
            return None
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to get Cloudflare zone: {str(e)}")
            return None

    def get_nameservers(self, zone_id: str) -> List[str]:
        """Get nameservers for a zone"""
        url = f"{self.base_url}/zones/{zone_id}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            self._log_api_response(response, f"get_nameservers(zone_id={zone_id})")
            
            if response.ok:
                data = response.json()
                if data.get('success'):
                    return data['result']['name_servers']
            return []
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to get nameservers: {str(e)}")
            return []

    def add_dns_records(self, zone_id: str, records: List[dict]) -> bool:
        """Add DNS records to a zone"""
        url = f"{self.base_url}/zones/{zone_id}/dns_records"
        success = True
        
        for record in records:
            try:
                response = requests.post(url, headers=self.headers, json=record, timeout=30)
                self._log_api_response(response, f"add_dns_record(zone_id={zone_id}, record={record})")
                
                if not response.ok or not response.json().get('success'):
                    success = False
                    print(f"❌ Failed to add DNS record: {record}")
                    print(f"Response: {response.text}")
                    
            except requests.exceptions.RequestException as e:
                success = False
                print(f"❌ Failed to add DNS record due to network error: {str(e)}")
                print(f"Record: {record}")
        
        return success

    def get_dns_records(self, zone_id: str, record_type: str = None) -> List[dict]:
        """Get existing DNS records for a zone"""
        url = f"{self.base_url}/zones/{zone_id}/dns_records"
        params = {}
        if record_type:
            params['type'] = record_type
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            self._log_api_response(response, f"get_dns_records(zone_id={zone_id})")
            
            if response.ok:
                data = response.json()
                if data.get('success'):
                    return data.get('result', [])
            return []
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to get DNS records: {str(e)}")
            return []

    def update_dns_record(self, zone_id: str, record_id: str, record_data: dict) -> bool:
        """Update an existing DNS record"""
        url = f"{self.base_url}/zones/{zone_id}/dns_records/{record_id}"
        
        try:
            response = requests.put(url, headers=self.headers, json=record_data, timeout=30)
            self._log_api_response(response, f"update_dns_record(zone_id={zone_id}, record_id={record_id})")
            
            if response.ok and response.json().get('success'):
                return True
            return False
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to update DNS record: {str(e)}")
            return False

    def delete_dns_record(self, zone_id: str, record_id: str) -> bool:
        """Delete a DNS record"""
        url = f"{self.base_url}/zones/{zone_id}/dns_records/{record_id}"
        
        try:
            response = requests.delete(url, headers=self.headers, timeout=30)
            self._log_api_response(response, f"delete_dns_record(zone_id={zone_id}, record_id={record_id})")
            
            if response.ok and response.json().get('success'):
                return True
            return False
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to delete DNS record: {str(e)}")
            return False

    def update_or_create_a_records(self, zone_id: str, server_ip: str, domain_name: str, log_callback=None) -> Tuple[bool, List[str]]:
        """
        Update existing A records or create new ones to point to the server IP.
        Returns: (success, list of log messages)
        """
        logs = []
        
        def log(msg):
            print(msg)
            logs.append(msg)
            if log_callback:
                log_callback(msg)
        
        # Get existing A records
        existing_records = self.get_dns_records(zone_id, record_type='A')
        log(f"Found {len(existing_records)} existing A records")
        
        # Records we need: @, www, *
        required_names = ['@', 'www', '*']
        existing_names = {}
        
        for record in existing_records:
            name = record.get('name', '')
            content = record.get('content', '')
            # Cloudflare returns full domain, convert to simple name
            if name == domain_name:
                existing_names['@'] = record
                log(f"  Found @ record: {content}")
            elif name == f'www.{domain_name}':
                existing_names['www'] = record
                log(f"  Found www record: {content}")
            elif name == f'*.{domain_name}':
                existing_names['*'] = record
                log(f"  Found * record: {content}")
        
        success = True
        updated_count = 0
        created_count = 0
        
        for name in required_names:
            record_data = {
                'type': 'A',
                'name': name,
                'content': server_ip,
                'ttl': 1,
                'proxied': False
            }
            
            if name in existing_names:
                existing = existing_names[name]
                old_ip = existing.get('content')
                # Check if IP is different
                if old_ip != server_ip:
                    log(f"🔄 Updating {name}: {old_ip} → {server_ip}")
                    if not self.update_dns_record(zone_id, existing['id'], record_data):
                        success = False
                        log(f"❌ FAILED to update A record for {name}")
                    else:
                        log(f"✅ Updated A record for {name}")
                        updated_count += 1
                else:
                    log(f"✓ {name} already points to {server_ip}")
            else:
                # Create new record
                log(f"➕ Creating A record for {name} → {server_ip}")
                url = f"{self.base_url}/zones/{zone_id}/dns_records"
                try:
                    response = requests.post(url, headers=self.headers, json=record_data, timeout=30)
                    if not response.ok or not response.json().get('success'):
                        success = False
                        log(f"❌ FAILED to create A record for {name}")
                        # Log the error response
                        try:
                            err = response.json()
                            log(f"   Error: {err.get('errors', [])}")
                        except:
                            pass
                    else:
                        log(f"✅ Created A record for {name}")
                        created_count += 1
                except Exception as e:
                    success = False
                    log(f"❌ Error creating A record for {name}: {e}")
        
        # Summary
        log(f"Summary: {updated_count} updated, {created_count} created, success={success}")
        
        return success, logs

class DomainManager:
    def __init__(self):
        # Load environment variables if .env file exists
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
        if os.path.exists(env_path):
            from dotenv import load_dotenv
            load_dotenv(env_path)
            print(f"Loaded environment variables from {env_path}")
        else:
            print("No .env file found, using default values")

        # Initialize clients
        self.cloudflare = CloudflareClient()
        self.namecheap = NamecheapClient()
        
        # Setup directories and configuration
        self.history_dir = os.path.join(os.getcwd(), 'history')
        os.makedirs(self.history_dir, exist_ok=True)
        self.server_ip = os.getenv('SERVER_IP', '65.109.63.240')
        
        print(f"\nDomain Manager initialized with:")
        print(f"History Directory: {self.history_dir}")
        print(f"Server IP: {self.server_ip}")

    def _log_message(self, domain_name: str, message: str, status: str = "info", site_id: str = None) -> None:
        """Log message to file with timestamp and status indicator"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = os.path.join(self.history_dir, f"{domain_name}_domain_live_process.log")
        
        if status == "error":
            prefix = "❌ ERROR: "
        elif status == "success":
            prefix = "✅ "
        else:
            prefix = "ℹ️ "
        
        log_entry = f"[{timestamp}] {prefix}{message}\n"
        
        with open(log_file, 'a') as f:
            f.write(log_entry)
            
        # If site_id is provided, emit WebSocket event
        if site_id:
            try:
                from flask_socketio import emit
                emit(f'log_update_{site_id}', {
                    'type': 'domain',
                    'status': status,
                    'message': message
                })
            except ImportError:
                print("Warning: flask_socketio not available, skipping WebSocket update")
            except Exception as e:
                print(f"Warning: Failed to emit WebSocket event: {str(e)}")

    def _log_command(self, domain_name: str, message: str, status: str = "info") -> None:
        """Alias for _log_message to maintain compatibility"""
        return self._log_message(domain_name, message, status)

    def _update_sites_json(self, domain_name: str, success: bool = True) -> None:
        """Update the sites.json file with domain setup status"""
        try:
            sites_file = "sites.json"
            sites_data = {}
            
            if os.path.exists(sites_file):
                with open(sites_file, 'r') as f:
                    sites_data = json.load(f)
            
            domain_id = None
            for id, site in sites_data.items():
                if site.get('domain_name') == domain_name:
                    domain_id = id
                    break
            
            if not domain_id:
                domain_id = str(uuid.uuid4())
            
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if domain_id in sites_data:
                sites_data[domain_id].update({
                    'domain_status': success,
                    'updated_at': current_time
                })
            else:
                port = os.getenv('DEFAULT_PORT', '3000')
                sites_data[domain_id] = {
                    'domain_name': domain_name,
                    'port': int(port),
                    'status': 'pending',
                    'IP_URL': f"http://{self.server_ip}:{port}",
                    'created_at': current_time,
                    'updated_at': current_time,
                    'domain_status': success,
                    'IP_live_status': False
                }
            
            with open(sites_file, 'w') as f:
                json.dump(sites_data, f, indent=4)
                
        except Exception as e:
            print(f"Warning: Failed to update sites.json: {str(e)}")

    def _prepare_dns_records(self, domain_name: str) -> List[dict]:
        """Prepare DNS records configuration"""
        return [
            {
                'type': 'A',
                'name': '@',
                'content': self.server_ip,
                'ttl': 1,
                'proxied': False
            },
            {
                'type': 'A',
                'name': 'www',
                'content': self.server_ip,
                'ttl': 1,
                'proxied': False
            },
            {
                'type': 'A',
                'name': '*',
                'content': self.server_ip,
                'ttl': 1,
                'proxied': False
            }
        ]

    def create_nginx_config(self, domain_name: str, site_id: str = None, port: int = 3000) -> Tuple[bool, str]:
        """Create Nginx configuration for the domain with SSL support"""
        try:
            # Get email from environment
            certbot_email = os.getenv('CERTBOT_EMAIL', os.getenv('ADMIN_EMAIL', 'admin@example.com'))
            cloudflare_ini_path = os.getenv('CLOUDFLARE_INI_PATH', '/etc/letsencrypt/cloudflare.ini')
            
            # Run certbot command to obtain SSL certificate (with lock to prevent concurrent runs)
            # Added --dns-cloudflare-propagation-seconds to wait for DNS propagation
            certbot_cmd = f'sudo certbot certonly --dns-cloudflare --dns-cloudflare-credentials {cloudflare_ini_path} --dns-cloudflare-propagation-seconds 30 -d {domain_name} -d "*.{domain_name}" --agree-tos --non-interactive -m {certbot_email}'
            
            self._log_message(domain_name, f"Waiting for certbot lock...", "info", site_id)
            
            # Use lock to ensure only one certbot runs at a time
            max_retries = 5
            base_delay = 15  # Base delay in seconds
            
            with certbot_lock:
                self._log_message(domain_name, f"Running certbot for SSL certificate...", "info", site_id)
                
                for attempt in range(max_retries):
                    try:
                        result = subprocess.run(certbot_cmd, shell=True, check=True, capture_output=True, text=True)
                        self._log_message(domain_name, "SSL certificate obtained successfully", "success", site_id)
                        if result.stdout:
                            self._log_message(domain_name, f"Certbot output: {result.stdout[:500]}", "info", site_id)
                        
                        # Add delay after successful certbot to prevent rate limiting
                        time.sleep(5)
                        break  # Success, exit retry loop
                        
                    except subprocess.CalledProcessError as e:
                        error_output = e.stderr if e.stderr else str(e)
                        
                        # Check for retryable errors
                        retryable_errors = [
                            "Another instance of Certbot is already running",
                            "Service busy",
                            "retry later",
                            "rate limit",
                            "too many requests"
                        ]
                        
                        is_retryable = any(err.lower() in error_output.lower() for err in retryable_errors)
                        
                        if is_retryable and attempt < max_retries - 1:
                            # Exponential backoff with jitter
                            retry_delay = base_delay * (2 ** attempt) + (attempt * 5)
                            self._log_message(domain_name, f"Certbot busy/rate-limited, waiting {retry_delay}s (attempt {attempt + 1}/{max_retries})...", "warning", site_id)
                            time.sleep(retry_delay)
                            continue
                        
                        error_msg = f"Failed to obtain SSL certificate: {error_output[:500]}"
                        self._log_message(domain_name, error_msg, "error", site_id)
                        self._log_message(domain_name, "Tip: Check /etc/letsencrypt/cloudflare.ini exists with correct API token", "info", site_id)
                        raise Exception(error_msg)

            nginx_config = f'''# Connection upgrade mapping
map $http_upgrade $connection_upgrade {{
    default upgrade;
    ""      close;
}}

# Redirect all HTTP traffic to HTTPS
server {{
    listen 80;
    server_name {domain_name} www.{domain_name} *.{domain_name};
    
    # Allow certbot challenge response
    location /.well-known/acme-challenge/ {{
        root /var/www/html;
    }}
    
    location / {{
        return 301 https://$host$request_uri;
    }}
}}

# Main HTTPS server block
server {{
    listen 443 ssl http2;
    server_name {domain_name} www.{domain_name} *.{domain_name};

    # SSL configuration
    ssl_certificate     /etc/letsencrypt/live/{domain_name}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{domain_name}/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;
    
    # SSL optimization
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;
    ssl_session_tickets off;
    
    # OCSP Stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 8.8.8.8 8.8.4.4 valid=300s;
    resolver_timeout 5s;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;

    # Proxy to application
    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }}
}}'''
            
            # Write config using sudo
            config_path = f"/etc/nginx/sites-available/{domain_name}"
            write_cmd = f"echo '{nginx_config}' | sudo tee {config_path} > /dev/null"
            try:
                subprocess.run(write_cmd, shell=True, check=True)
                self._log_message(domain_name, f"Created Nginx config file at {config_path}", "success", site_id)
            except subprocess.CalledProcessError as e:
                error_msg = f"Failed to create Nginx config file: {str(e)}"
                self._log_message(domain_name, error_msg, "error", site_id)
                raise Exception(error_msg)

            # Create symbolic link using sudo
            symlink_path = f"/etc/nginx/sites-enabled/{domain_name}"
            if not os.path.exists(symlink_path):
                try:
                    subprocess.run(["sudo", "ln", "-s", config_path, symlink_path], check=True)
                    self._log_message(domain_name, f"Created symbolic link at {symlink_path}", "success", site_id)
                except subprocess.CalledProcessError as e:
                    error_msg = f"Failed to create symbolic link: {str(e)}"
                    self._log_message(domain_name, error_msg, "error", site_id)
                    raise Exception(error_msg)

            # Test Nginx configuration
            try:
                result = subprocess.run(["sudo", "nginx", "-t"], capture_output=True, text=True, check=True)
                self._log_message(domain_name, "Nginx configuration test passed", "success", site_id)
            except subprocess.CalledProcessError as e:
                error_msg = f"Nginx configuration test failed: {e.stderr}"
                self._log_message(domain_name, error_msg, "error", site_id)
                raise Exception(error_msg)

            # Reload Nginx
            try:
                subprocess.run(["sudo", "systemctl", "reload", "nginx"], check=True)
                self._log_message(domain_name, "Nginx service reloaded successfully", "success", site_id)
            except subprocess.CalledProcessError as e:
                error_msg = f"Failed to reload Nginx: {str(e)}"
                self._log_message(domain_name, error_msg, "error", site_id)
                raise Exception(error_msg)

            return True, f"✅ Nginx configuration created and loaded for {domain_name}"
        except Exception as e:
            return False, f"Failed to create Nginx config: {str(e)}"

    def setup_domain(self, domain_name: str, site_id: str = None) -> Tuple[bool, str]:
        """Setup domain with Cloudflare and Namecheap integration"""
        try:
            # Validate domain name format
            if not validate_domain_name(domain_name):
                raise ValueError("Invalid domain name format")
                
            self._log_message(domain_name, "Starting domain setup process...", "info", site_id)
            
            # Step 1: Check if Cloudflare zone exists
            zone_id = self.cloudflare.get_zone(domain_name)
            if zone_id:
                self._log_message(domain_name, "Found existing Cloudflare zone", "success", site_id)
                
                # Update or create A records to point to the correct server IP
                self._log_message(domain_name, f"Checking A records to ensure they point to {self.server_ip}...", "info", site_id)
                a_record_success, a_record_logs = self.cloudflare.update_or_create_a_records(zone_id, self.server_ip, domain_name)
                # Show detailed A record logs
                for log_line in a_record_logs:
                    status = "success" if "✅" in log_line or "✓" in log_line else ("error" if "❌" in log_line else "info")
                    self._log_message(domain_name, log_line, status, site_id)
                if not a_record_success:
                    self._log_message(domain_name, "⚠️ Some A records may not have been updated", "warning", site_id)
                else:
                    self._log_message(domain_name, f"A records verified/updated to point to {self.server_ip}", "success", site_id)
                
                # Get existing nameservers from Cloudflare
                nameservers = self.cloudflare.get_nameservers(zone_id)
                if not nameservers:
                    raise Exception("Failed to get Cloudflare nameservers")
                self._log_message(domain_name, f"Retrieved Cloudflare nameservers: {', '.join(nameservers)}", "success", site_id)
                
                # Try to update Namecheap nameservers (non-blocking if fails)
                if not self.namecheap.set_nameservers(domain_name, nameservers):
                    self._log_message(domain_name, "⚠️ Could not auto-update Namecheap nameservers", "warning", site_id)
                    self._log_message(domain_name, "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "warning", site_id)
                    self._log_message(domain_name, "🔧 MANUAL ACTION REQUIRED:", "warning", site_id)
                    self._log_message(domain_name, f"   Add these nameservers to your domain registrar:", "warning", site_id)
                    for ns in nameservers:
                        self._log_message(domain_name, f"   → {ns}", "warning", site_id)
                    self._log_message(domain_name, "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "warning", site_id)
                    self._log_message(domain_name, "Continuing with Cloudflare setup...", "info", site_id)
                else:
                    self._log_message(domain_name, "Updated Namecheap nameservers for existing Cloudflare zone", "success", site_id)
                # Get port from sites.json
                port = 3000  # default port
                try:
                    with open("sites.json", 'r') as f:
                        sites_data = json.load(f)
                        # Find the site entry by domain name
                        for site in sites_data.values():
                            if site.get('domain_name') == domain_name:
                                port = site.get('port', 3000)
                                break
                    self._log_message(domain_name, f"Retrieved port {port} from sites.json", "success", site_id)
                except Exception as e:
                    self._log_message(domain_name, f"Failed to get port from sites.json, using default port 3000: {str(e)}", "info", site_id)

                # Create Nginx configuration with the retrieved port
                success, message = self.create_nginx_config(domain_name, site_id, port)
                if not success:
                    raise Exception(f"Failed to create Nginx configuration: {message}")
                self._log_message(domain_name, f"Created Nginx configuration with port {port}", "success", site_id)
                
            else:
                # Create new zone if it doesn't exist
                zone_id = self.cloudflare.create_zone(domain_name)
                if not zone_id:
                    raise Exception("Failed to create Cloudflare zone")
                self._log_message(domain_name, "Created new Cloudflare zone", "success", site_id)

                # Add DNS records for new zone
                dns_records = self._prepare_dns_records(domain_name)
                if not self.cloudflare.add_dns_records(zone_id, dns_records):
                    raise Exception("Failed to add DNS records")
                self._log_message(domain_name, "Added DNS records", "success", site_id)

                # Get nameservers for new zone
                nameservers = self.cloudflare.get_nameservers(zone_id)
                if not nameservers:
                    raise Exception("Failed to get Cloudflare nameservers")
                self._log_message(domain_name, f"Retrieved Cloudflare nameservers: {', '.join(nameservers)}", "success", site_id)

                # Try to update Namecheap nameservers (non-blocking if fails)
                if not self.namecheap.set_nameservers(domain_name, nameservers):
                    self._log_message(domain_name, "⚠️ Could not auto-update Namecheap nameservers", "warning", site_id)
                    self._log_message(domain_name, "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "warning", site_id)
                    self._log_message(domain_name, "🔧 MANUAL ACTION REQUIRED:", "warning", site_id)
                    self._log_message(domain_name, f"   Add these nameservers to your domain registrar:", "warning", site_id)
                    for ns in nameservers:
                        self._log_message(domain_name, f"   → {ns}", "warning", site_id)
                    self._log_message(domain_name, "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "warning", site_id)
                    self._log_message(domain_name, "Continuing with Nginx/SSL setup...", "info", site_id)
                else:
                    self._log_message(domain_name, "Updated Namecheap nameservers", "success", site_id)

                # Get port from sites.json
                port = 3000  # default port
                try:
                    with open("sites.json", 'r') as f:
                        sites_data = json.load(f)
                        # Find the site entry by domain name
                        for site in sites_data.values():
                            if site.get('domain_name') == domain_name:
                                port = site.get('port', 3000)
                                break
                    self._log_message(domain_name, f"Retrieved port {port} from sites.json", "success", site_id)
                except Exception as e:
                    self._log_message(domain_name, f"Failed to get port from sites.json, using default port 3000: {str(e)}", "info", site_id)

                # Create Nginx configuration with the retrieved port
                success, message = self.create_nginx_config(domain_name, site_id, port)
                if not success:
                    raise Exception(f"Failed to create Nginx configuration: {message}")
                self._log_message(domain_name, f"Created Nginx configuration with port {port}", "success", site_id)

            # Update sites.json
            self._update_sites_json(domain_name, True)
            self._log_message(domain_name, "Updated sites.json", "success", site_id)

            # Final success message
            success_msg = "Domain setup completed successfully"
            self._log_message(domain_name, success_msg, "success", site_id)
            return True, success_msg

        except Exception as e:
            error_msg = str(e)
            self._log_message(domain_name, error_msg, "error", site_id)
            self._update_sites_json(domain_name, False)
            return False, error_msg

    def update_domain_dns_ssl(self, domain_name: str, site_id: str = None, port: int = 3000) -> Tuple[bool, str]:
        """
        Update domain: refresh Cloudflare A records to point to server IP and reinstall SSL certificate.
        This is useful when:
        - Server IP has changed
        - SSL certificate needs renewal
        - A records are pointing to wrong IP
        """
        try:
            # Validate domain name format
            if not validate_domain_name(domain_name):
                raise ValueError("Invalid domain name format")
                
            self._log_message(domain_name, "Starting domain update (DNS + SSL)...", "info", site_id)
            
            # Step 1: Get or create Cloudflare zone
            zone_id = self.cloudflare.get_zone(domain_name)
            if not zone_id:
                self._log_message(domain_name, "Cloudflare zone not found, creating new zone...", "info", site_id)
                zone_id = self.cloudflare.create_zone(domain_name)
                if not zone_id:
                    raise Exception("Failed to create Cloudflare zone")
                self._log_message(domain_name, "Created new Cloudflare zone", "success", site_id)
            else:
                self._log_message(domain_name, "Found existing Cloudflare zone", "success", site_id)
            
            # Step 2: Update A records to point to server IP
            self._log_message(domain_name, f"Updating A records to point to {self.server_ip}...", "info", site_id)
            a_record_success, a_record_logs = self.cloudflare.update_or_create_a_records(zone_id, self.server_ip, domain_name)
            # Show detailed A record logs
            for log_line in a_record_logs:
                status = "success" if "✅" in log_line or "✓" in log_line else ("error" if "❌" in log_line else "info")
                self._log_message(domain_name, log_line, status, site_id)
            if a_record_success:
                self._log_message(domain_name, f"✅ A records updated to {self.server_ip}", "success", site_id)
            else:
                self._log_message(domain_name, "⚠️ Some A records may not have been updated", "warning", site_id)
            
            # Step 3: Get nameservers (for reference)
            nameservers = self.cloudflare.get_nameservers(zone_id)
            if nameservers:
                self._log_message(domain_name, f"Cloudflare nameservers: {', '.join(nameservers)}", "info", site_id)
            
            # Step 4: Reinstall SSL certificate
            self._log_message(domain_name, "Reinstalling SSL certificate...", "info", site_id)
            success, message = self.create_nginx_config(domain_name, site_id, port)
            
            if not success:
                raise Exception(f"Failed to reinstall SSL: {message}")
            
            self._log_message(domain_name, "✅ SSL certificate reinstalled successfully", "success", site_id)
            
            # Update sites.json
            self._update_sites_json(domain_name, True)
            
            # Final success message
            success_msg = "Domain update completed: A records updated & SSL reinstalled"
            self._log_message(domain_name, success_msg, "success", site_id)
            return True, success_msg

        except Exception as e:
            error_msg = str(e)
            self._log_message(domain_name, f"Domain update failed: {error_msg}", "error", site_id)
            return False, error_msg