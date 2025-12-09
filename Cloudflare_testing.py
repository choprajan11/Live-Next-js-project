import requests
import time
# -------------------------------
# CONFIGURATION
# -------------------------------
API_TOKEN = "5Cky6x43POBEyloqJhgdCGT37jtVImhneiDup0no"
ACCOUNT_ID = "cde8c95ccae7ecdcd32ae3d98b61f45a"

NEW_DOMAIN = "bigsargejunkremoval.com"     # Replace with the domain you want to add
SERVER_IP = "123.123.123.123" # Replace with your server IP

BASE_URL = "https://api.cloudflare.com/client/v4"

headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json",
}


txt_record = "arioejfskdfjidfskdanklsadjjiojiioi"
# -------------------------------
# STEP 1: Add new domain (zone)
# -------------------------------
def add_domain():
    url = f"{BASE_URL}/zones"
    payload = {
        "name": NEW_DOMAIN,
        "account": {"id": ACCOUNT_ID},
        "jump_start": True  # Cloudflare scans for existing DNS records
    }
    response = requests.post(url, headers=headers, json=payload)
    data = response.json()
    
    if response.status_code in [200, 201]:
        zone_id = data["result"]["id"]
        print(f"✅ Domain added: {NEW_DOMAIN}, Zone ID: {zone_id}")
        return zone_id
    else:
        print("❌ Error adding domain:", data)
        return None

# -------------------------------
# STEP 2: Add DNS record (A @ → IP)
# -------------------------------
def add_dns_record(zone_id, retries=3, delay=5):
    url = f"{BASE_URL}/zones/{zone_id}/dns_records"
    payload = {
            "type": "TXT",
            "name": "@",
            "content": txt_record
        }

    for attempt in range(1, retries+1):
        time.sleep(delay)
        response = requests.post(url, headers=headers, json=payload)
        data = response.json()

        if response.status_code in [200, 201] and data.get("success", False):
            print(f"✅ DNS Record added: {NEW_DOMAIN} -> {SERVER_IP}")
            return True
        else:
            print(f"⚠️ Attempt {attempt} failed: {data}")
            if attempt < retries:
                print(f"⏳ Waiting {delay} seconds before retry...")
                time.sleep(delay)
    
    print("❌ Error adding DNS record after retries")
    return False

def get_zone_id(domain_name):
    url = f"{BASE_URL}/zones"
    params = {
        "name": domain_name,
        "status": "active"
    }
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    
    if response.status_code == 200 and data.get("result"):
        zone_id = data["result"][0]["id"]
        print(f"✅ Found zone ID for domain: {domain_name}, Zone ID: {zone_id}")
        return zone_id
    else:
        print(f"❌ Error getting zone ID for domain {domain_name}:", data.get("errors", "No specific error message"))
        return None

# -------------------------------
# RUN SCRIPT
# -------------------------------
if __name__ == "__main__":
    zone_id = get_zone_id(NEW_DOMAIN)
    if zone_id:
        print(zone_id)
        # add_dns_record(zone_id)
