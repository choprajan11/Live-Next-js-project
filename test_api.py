import unittest
import requests
import os
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class TestSiteAPI(unittest.TestCase):
    def setUp(self):
        """Set up test case"""
        self.base_url = "http://65.109.63.240:5000/api/v1"  # Update with your server URL
        self.api_key = os.getenv('API_KEY')
        self.headers = {
            'X-API-Key': self.api_key,
            'Content-Type': 'application/json'
        }
        
        # Test data
        self.test_site = {
            "repo": "https://github.com/kingsgrimbyte/whitts-plumbing.git",
            "domain": "whittsplumbing.com",
            "name": "whittsplumbing.com"
        }
        self.site_id = None

    def test_1_create_site(self):
        """Test creating a new site"""
        # Make POST request to create site
        response = requests.post(
            f"{self.base_url}/sites",
            headers=self.headers,
            json=self.test_site
        )
        
        # Assert response status code is 201 (Created)
        self.assertEqual(response.status_code, 201)
        
        # Assert response contains success status and site_id
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('data', data)
        self.assertIn('site_id', data['data'])
        
        # Store site_id for later tests
        TestSiteAPI.site_id = data['data']['site_id']

    def test_2_get_site(self):
        """Test getting the created site details"""
        if not hasattr(TestSiteAPI, 'site_id'):
            self.skipTest("Site ID not available")
        
        response = requests.get(
            f"{self.base_url}/sites/{TestSiteAPI.site_id}",
            headers=self.headers
        )
        
        # Assert response status code is 200
        self.assertEqual(response.status_code, 200)
        
        # Assert response contains correct site data
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['data']['domain_name'], self.test_site['domain'])
        self.assertEqual(data['data']['repo'], self.test_site['repo'])
        self.assertEqual(data['data']['name'], self.test_site['name'])

    def test_3_deploy_site(self):
        """Test deploying the site"""
        if not hasattr(TestSiteAPI, 'site_id'):
            self.skipTest("Site ID not available")
        
        response = requests.post(
            f"{self.base_url}/sites/{TestSiteAPI.site_id}/deploy",
            headers=self.headers
        )
        
        # Assert response status code is 200
        self.assertEqual(response.status_code, 200)
        
        # Assert response contains success status
        data = response.json()
        self.assertIn('status', data)
        # Note: The actual deployment might fail due to invalid test repo
        # so we don't assert success here, just check for status field

    def test_4_setup_domain(self):
        """Test setting up domain for the site"""
        if not hasattr(TestSiteAPI, 'site_id'):
            self.skipTest("Site ID not available")
        
        response = requests.post(
            f"{self.base_url}/sites/{TestSiteAPI.site_id}/domain",
            headers=self.headers
        )
        
        # Assert response status code is 200
        self.assertEqual(response.status_code, 200)
        
        # Assert response contains required fields
        data = response.json()
        self.assertIn('status', data)
        self.assertIn('message', data)
        self.assertIn('url', data)
        
        # If successful, verify the URL format
        if data['status'] == 'success':
            self.assertTrue(data['url'].startswith('https://'))
            self.assertEqual(
                data['url'], 
                f"https://{self.test_site['domain']}"
            )
        
        # Note: The actual domain setup might fail due to various reasons
        # so we don't assert success here, just check for required fields

def tearDown(self):
    """Clean up after tests"""
    # You might want to add cleanup code here
    # For example, deleting the test site from sites.json
    pass

if __name__ == '__main__':
    unittest.main()
