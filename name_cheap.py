#!/usr/bin/env python3
"""
namecheap_setns.py
- Detects your public IPv4 and prints instructions to whitelist it in Namecheap.
- Tries to call namecheap.domains.dns.setCustom (will fail unless IP is whitelisted).
NOTE: Put real secrets in environment variables, not in the script.
"""

import os
import requests
import sys
from urllib.parse import urlencode

# ----- Configuration (use environment variables for safety) -----
API_USER = os.environ.get("NAMECHEAP_API_USER", "Kingsgrimbyte")
API_KEY  = os.environ.get("NAMECHEAP_API_KEY", "e8ba57c4e9d848c4b8fe08f56f7ec8cc")
USERNAME = os.environ.get("NAMECHEAP_USERNAME", "Kingsgrimbyte")
DOMAIN   = os.environ.get("NAMECHEAP_DOMAIN", "bigsargejunkremoval.com")
NAMESERVERS = os.environ.get("NAMECHEAP_NAMESERVERS",
                              "barbara.ns.cloudflare.com,vasilii.ns.cloudflare.com")
API_URL  = "https://api.namecheap.com/xml.response"

# ----- Step 1: Get public IP (IPv4) -----
def get_public_ip():
    # multiple fallback services - choose the first that responds
    services = [
        "https://api.ipify.org?format=json",
        "https://ifconfig.me/all.json",
        "https://ipinfo.io/json"
    ]
    for s in services:
        try:
            r = requests.get(s, timeout=6)
            r.raise_for_status()
            data = r.json()
            # ip key differs by service
            for key in ("ip", "ip_addr", "ip_address"):
                if key in data:
                    return data[key]
            # ipinfo uses 'ip'
            if "ip" in data:
                return data["ip"]
            # fallback: some services return 'ip_address' etc.
            # if not found, try parse text (for ipify the query returns JSON, but if text fallback)
            text = r.text.strip()
            if text and all(c.isdigit() or c=='.' for c in text):
                return text
        except Exception:
            continue
    raise RuntimeError("Unable to determine public IP. Check network or the IP services used.")

# ----- Step 2: Build and (optionally) perform Namecheap API request -----
def namecheap_set_custom_nameservers(sld, tld, client_ip, debug=True):
    params = {
        "ApiUser": API_USER,
        "ApiKey": API_KEY,
        "UserName": USERNAME,
        "ClientIp": client_ip,
        "Command": "namecheap.domains.dns.setCustom",
        "SLD": sld,
        "TLD": tld,
        "NameServers": NAMESERVERS
    }
    full_url = API_URL + "?" + urlencode(params)
    if debug:
        print("\n[DEBUG] Request URL (hidden ApiKey in print):")
        # show without ApiKey for safety
        safe_params = params.copy()
        safe_params["ApiKey"] = "*****REDACTED*****"
        print(API_URL + "?" + urlencode(safe_params))
    try:
        resp = requests.get(API_URL, params=params, timeout=15)
        resp.raise_for_status()
        return resp.text
    except requests.HTTPError as e:
        return f"HTTP error: {e} - response text:\n{getattr(e.response, 'text', '')}"
    except Exception as e:
        return f"Request failed: {e}"

# ----- Main -----
def main():
    print("Step 1: Detecting public IPv4 address...")
    try:
        public_ip = get_public_ip()
    except Exception as e:
        print("Could not detect public IP:", e)
        sys.exit(1)

    print(f"\nYour public IPv4: {public_ip}")
    print("\nIMPORTANT: You must add this IP to your Namecheap account's API Whitelist.")
    print("Go to Namecheap → Profile → Tools → Namecheap API Access → Edit Whitelisted IPs → Add this IPv4 and Save.")
    print("Docs: https://www.namecheap.com/support/api/intro/")

    # Offer to proceed with the API call (attempt); it will fail unless the IP is whitelisted.
    proceed = os.environ.get("NAMECHEAP_SKIP_CALL", "").lower() not in ("1", "true", "yes")
    if not proceed:
        print("\nSkipping actual API call because NAMECHEAP_SKIP_CALL is set.")
        return

    print("\nAttempting Namecheap API request (will only succeed if the IP is whitelisted)...")
    sld, tld = DOMAIN.split(".", 1)[0], DOMAIN.split(".", 1)[1]
    result = namecheap_set_custom_nameservers(sld, tld, client_ip=public_ip)
    print("\n---- API RESPONSE ----")
    print(result)
    print("---- End response ----\n")
    print("If response contains an error about Client IP or authentication, re-check that the IP is whitelisted and the ApiUser/ApiKey are correct.")

if __name__ == "__main__":
    main()