import os
import json
import threading
import queue
import time
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

from models.site_live import SiteLiveManager
from models.add_domain import DomainManager


class BulkDeploymentManager:
    """
    Manages bulk deployment of multiple Next.js sites.
    Supports parallel processing with configurable concurrency.
    """
    
    def __init__(self, max_workers: int = 3):
        self.site_manager = SiteLiveManager()
        self.domain_manager = DomainManager()
        self.max_workers = max_workers
        self.sites_json_path = os.getenv('SITES_JSON_PATH', 'sites.json')
        
        # Deployment state
        self.is_running = False
        self.should_stop = False
        self.current_batch_id = None
        self.progress = {}
        self.logs = {}
        
        # History directory for bulk logs
        self.history_dir = os.path.join(os.getcwd(), 'history', 'bulk')
        os.makedirs(self.history_dir, exist_ok=True)
        
        # Callback for real-time updates
        self.on_progress_update: Optional[Callable] = None
        self.on_log_update: Optional[Callable] = None
    
    def _log(self, batch_id: str, message: str, status: str = "info", site_name: str = None):
        """Log message to file and trigger callback"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if status == "error":
            prefix = "❌ ERROR"
        elif status == "success":
            prefix = "✅"
        elif status == "warning":
            prefix = "⚠️"
        else:
            prefix = "ℹ️"
        
        site_prefix = f"[{site_name}] " if site_name else ""
        log_entry = f"[{timestamp}] {prefix} {site_prefix}{message}"
        
        # Store in memory
        if batch_id not in self.logs:
            self.logs[batch_id] = []
        self.logs[batch_id].append(log_entry)
        
        # Write to file
        log_file = os.path.join(self.history_dir, f"{batch_id}_bulk_deploy.log")
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry + "\n")
        
        # Trigger callback
        if self.on_log_update:
            self.on_log_update(batch_id, log_entry, status, site_name)
        
        return log_entry
    
    def _update_progress(self, batch_id: str, site_name: str, step: str, status: str):
        """Update progress for a site"""
        if batch_id not in self.progress:
            self.progress[batch_id] = {"sites": {}, "summary": {}}
        
        self.progress[batch_id]["sites"][site_name] = {
            "step": step,
            "status": status,
            "updated_at": datetime.now().isoformat()
        }
        
        # Update summary
        sites = self.progress[batch_id]["sites"]
        self.progress[batch_id]["summary"] = {
            "total": len(sites),
            "pending": sum(1 for s in sites.values() if s["status"] == "pending"),
            "in_progress": sum(1 for s in sites.values() if s["status"] == "in_progress"),
            "completed": sum(1 for s in sites.values() if s["status"] == "completed"),
            "failed": sum(1 for s in sites.values() if s["status"] == "failed"),
            "skipped": sum(1 for s in sites.values() if s["status"] == "skipped")
        }
        
        # Trigger callback
        if self.on_progress_update:
            self.on_progress_update(batch_id, self.progress[batch_id])
    
    def get_progress(self, batch_id: str) -> Dict:
        """Get current progress for a batch"""
        return self.progress.get(batch_id, {"sites": {}, "summary": {}})
    
    def get_logs(self, batch_id: str) -> List[str]:
        """Get logs for a batch"""
        return self.logs.get(batch_id, [])
    
    def scan_github_repos(self, github_token: str, username: str = None, org: str = None) -> List[Dict]:
        """
        Scan GitHub for Next.js repositories.
        Returns list of repos that appear to be Next.js projects.
        """
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        repos = []
        page = 1
        
        # Determine endpoint based on username or org
        if org:
            base_url = f"https://api.github.com/orgs/{org}/repos"
        elif username:
            base_url = f"https://api.github.com/users/{username}/repos"
        else:
            base_url = "https://api.github.com/user/repos"
        
        while True:
            try:
                response = requests.get(
                    base_url,
                    headers=headers,
                    params={"page": page, "per_page": 100, "type": "all"},
                    timeout=30
                )
                response.raise_for_status()
                
                page_repos = response.json()
                if not page_repos:
                    break
                
                for repo in page_repos:
                    # Check if it's a Next.js project by looking for package.json
                    try:
                        pkg_response = requests.get(
                            f"https://api.github.com/repos/{repo['full_name']}/contents/package.json",
                            headers=headers,
                            timeout=10
                        )
                        if pkg_response.status_code == 200:
                            import base64
                            content = json.loads(base64.b64decode(pkg_response.json()['content']))
                            
                            # Check for Next.js
                            deps = {**content.get('dependencies', {}), **content.get('devDependencies', {})}
                            if 'next' in deps:
                                repos.append({
                                    "name": repo['name'],
                                    "full_name": repo['full_name'],
                                    "clone_url": repo['clone_url'],
                                    "ssh_url": repo['ssh_url'],
                                    "default_branch": repo.get('default_branch', 'main'),
                                    "next_version": deps.get('next', 'unknown'),
                                    "private": repo['private']
                                })
                    except Exception:
                        continue
                
                page += 1
                time.sleep(0.5)  # Rate limiting
                
            except requests.exceptions.RequestException as e:
                print(f"GitHub API error: {e}")
                break
        
        return repos
    
    def import_sites_from_json(self, json_data: List[Dict]) -> Tuple[int, int, List[str]]:
        """
        Import sites from JSON data.
        Expected format: [{"domain": "example.com", "repo": "https://github.com/...", "name": "Site Name"}, ...]
        Returns: (imported_count, skipped_count, errors)
        """
        imported = 0
        skipped = 0
        errors = []
        
        # Load existing sites
        existing_domains = set()
        if os.path.exists(self.sites_json_path):
            with open(self.sites_json_path, 'r') as f:
                sites_data = json.load(f)
                for site in sites_data.values():
                    existing_domains.add(site.get('domain_name', '').lower())
        
        for site in json_data:
            try:
                domain = site.get('domain', '').lower().strip()
                repo = site.get('repo', '').strip()
                name = site.get('name', domain)
                
                if not domain or not repo:
                    errors.append(f"Missing domain or repo: {site}")
                    continue
                
                if domain in existing_domains:
                    skipped += 1
                    continue
                
                # Get next port
                port = self.site_manager._get_next_port()
                
                # Create site entry
                site_id = self.site_manager._generate_site_id()
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                site_info = {
                    "domain_name": domain,
                    "port": port,
                    "status": "pending",
                    "IP_URL": f"http://localhost:{port}",
                    "created_at": current_time,
                    "updated_at": current_time,
                    "domain_status": False,
                    "domain_provider": "namecheap",
                    "IP_live_status": False,
                    "repo": repo,
                    "project_dir": "",
                    "name": name
                }
                
                # Load and update sites.json
                sites_data = {}
                if os.path.exists(self.sites_json_path):
                    with open(self.sites_json_path, 'r') as f:
                        sites_data = json.load(f)
                
                sites_data[site_id] = site_info
                
                with open(self.sites_json_path, 'w') as f:
                    json.dump(sites_data, f, indent=4)
                
                existing_domains.add(domain)
                imported += 1
                
            except Exception as e:
                errors.append(f"Error importing {site}: {str(e)}")
        
        return imported, skipped, errors
    
    def export_sites_to_json(self, status_filter: str = None) -> List[Dict]:
        """
        Export sites to JSON format.
        Optional status_filter: 'pending', 'live', 'all'
        """
        if not os.path.exists(self.sites_json_path):
            return []
        
        with open(self.sites_json_path, 'r') as f:
            sites_data = json.load(f)
        
        result = []
        for site_id, site in sites_data.items():
            if status_filter and status_filter != 'all':
                if status_filter == 'pending' and site.get('IP_live_status', False):
                    continue
                if status_filter == 'live' and not site.get('IP_live_status', False):
                    continue
            
            result.append({
                "id": site_id,
                "domain": site.get('domain_name', ''),
                "repo": site.get('repo', ''),
                "name": site.get('name', site.get('domain_name', '')),
                "port": site.get('port'),
                "status": site.get('status'),
                "IP_live_status": site.get('IP_live_status', False),
                "domain_status": site.get('domain_status', False)
            })
        
        return result
    
    def _deploy_single_site(self, batch_id: str, site_id: str, site_info: Dict, 
                           deploy_local: bool = True, setup_domain: bool = False) -> Tuple[bool, str]:
        """Deploy a single site (used by bulk deploy)"""
        domain_name = site_info.get('domain_name', '')
        repo = site_info.get('repo', '')
        
        try:
            self._update_progress(batch_id, domain_name, "starting", "in_progress")
            self._log(batch_id, f"Starting deployment", "info", domain_name)
            
            if self.should_stop:
                self._update_progress(batch_id, domain_name, "stopped", "skipped")
                return False, "Deployment stopped by user"
            
            # Step 1: Local deployment (git clone, npm install, build, pm2)
            if deploy_local:
                self._update_progress(batch_id, domain_name, "deploying_local", "in_progress")
                self._log(batch_id, f"Deploying locally...", "info", domain_name)
                
                result = self.site_manager.deploy_site(domain_name, repo)
                
                if result['status'] != 'success':
                    self._update_progress(batch_id, domain_name, "local_failed", "failed")
                    self._log(batch_id, f"Local deployment failed: {result.get('message', 'Unknown error')}", "error", domain_name)
                    return False, result.get('message', 'Local deployment failed')
                
                self._log(batch_id, f"Local deployment successful", "success", domain_name)
            
            if self.should_stop:
                self._update_progress(batch_id, domain_name, "stopped", "skipped")
                return False, "Deployment stopped by user"
            
            # Step 2: Domain setup (Cloudflare, Namecheap, Nginx, SSL)
            if setup_domain:
                self._update_progress(batch_id, domain_name, "setting_up_domain", "in_progress")
                self._log(batch_id, f"Setting up domain...", "info", domain_name)
                
                success, message = self.domain_manager.setup_domain(domain_name, site_id)
                
                if not success:
                    self._update_progress(batch_id, domain_name, "domain_failed", "failed")
                    self._log(batch_id, f"Domain setup failed: {message}", "error", domain_name)
                    return False, f"Domain setup failed: {message}"
                
                self._log(batch_id, f"Domain setup successful", "success", domain_name)
            
            self._update_progress(batch_id, domain_name, "completed", "completed")
            self._log(batch_id, f"Deployment completed successfully", "success", domain_name)
            return True, "Deployment completed successfully"
            
        except Exception as e:
            self._update_progress(batch_id, domain_name, "error", "failed")
            self._log(batch_id, f"Deployment error: {str(e)}", "error", domain_name)
            return False, str(e)
    
    def start_bulk_deploy(self, site_ids: List[str] = None, deploy_local: bool = True, 
                         setup_domain: bool = False, status_filter: str = "pending") -> str:
        """
        Start bulk deployment.
        
        Args:
            site_ids: Specific site IDs to deploy. If None, deploys based on status_filter.
            deploy_local: Whether to deploy locally (git, npm, pm2)
            setup_domain: Whether to setup domain (Cloudflare, Nginx, SSL)
            status_filter: Filter sites by status ('pending', 'all')
        
        Returns:
            batch_id: Unique ID for this bulk deployment batch
        """
        if self.is_running:
            raise Exception("A bulk deployment is already running")
        
        # Generate batch ID
        batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_batch_id = batch_id
        self.is_running = True
        self.should_stop = False
        self.progress[batch_id] = {"sites": {}, "summary": {}}
        self.logs[batch_id] = []
        
        # Load sites
        if not os.path.exists(self.sites_json_path):
            raise Exception("No sites.json found")
        
        with open(self.sites_json_path, 'r') as f:
            sites_data = json.load(f)
        
        # Filter sites
        sites_to_deploy = []
        for site_id, site_info in sites_data.items():
            if site_ids and site_id not in site_ids:
                continue
            
            if not site_ids and status_filter == "pending":
                if site_info.get('IP_live_status', False):
                    continue
            
            sites_to_deploy.append((site_id, site_info))
        
        if not sites_to_deploy:
            self.is_running = False
            raise Exception("No sites to deploy")
        
        self._log(batch_id, f"Starting bulk deployment of {len(sites_to_deploy)} sites", "info")
        self._log(batch_id, f"Max parallel workers: {self.max_workers}", "info")
        self._log(batch_id, f"Deploy local: {deploy_local}, Setup domain: {setup_domain}", "info")
        
        # Initialize progress for all sites
        for site_id, site_info in sites_to_deploy:
            domain_name = site_info.get('domain_name', '')
            self._update_progress(batch_id, domain_name, "queued", "pending")
        
        # Start deployment in background thread
        def run_deployments():
            try:
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    futures = {}
                    
                    for site_id, site_info in sites_to_deploy:
                        if self.should_stop:
                            break
                        
                        future = executor.submit(
                            self._deploy_single_site,
                            batch_id, site_id, site_info,
                            deploy_local, setup_domain
                        )
                        futures[future] = site_info.get('domain_name', '')
                    
                    for future in as_completed(futures):
                        domain_name = futures[future]
                        try:
                            success, message = future.result()
                        except Exception as e:
                            self._log(batch_id, f"Unexpected error: {str(e)}", "error", domain_name)
                
                # Final summary
                summary = self.progress[batch_id]["summary"]
                self._log(batch_id, "=" * 50, "info")
                self._log(batch_id, "BULK DEPLOYMENT COMPLETED", "success")
                self._log(batch_id, f"Total: {summary.get('total', 0)}", "info")
                self._log(batch_id, f"Completed: {summary.get('completed', 0)}", "success")
                self._log(batch_id, f"Failed: {summary.get('failed', 0)}", "error" if summary.get('failed', 0) > 0 else "info")
                self._log(batch_id, f"Skipped: {summary.get('skipped', 0)}", "warning" if summary.get('skipped', 0) > 0 else "info")
                self._log(batch_id, "=" * 50, "info")
                
            finally:
                self.is_running = False
                self.current_batch_id = None
        
        thread = threading.Thread(target=run_deployments, daemon=True)
        thread.start()
        
        return batch_id
    
    def stop_bulk_deploy(self) -> bool:
        """Stop the current bulk deployment"""
        if not self.is_running:
            return False
        
        self.should_stop = True
        if self.current_batch_id:
            self._log(self.current_batch_id, "Stop requested - waiting for current deployments to finish", "warning")
        return True
    
    def get_status(self) -> Dict:
        """Get current bulk deployment status"""
        return {
            "is_running": self.is_running,
            "current_batch_id": self.current_batch_id,
            "should_stop": self.should_stop
        }
    
    def get_pending_sites_count(self) -> int:
        """Get count of sites pending deployment"""
        if not os.path.exists(self.sites_json_path):
            return 0
        
        with open(self.sites_json_path, 'r') as f:
            sites_data = json.load(f)
        
        return sum(1 for site in sites_data.values() if not site.get('IP_live_status', False))
    
    def get_live_sites_count(self) -> int:
        """Get count of live sites"""
        if not os.path.exists(self.sites_json_path):
            return 0
        
        with open(self.sites_json_path, 'r') as f:
            sites_data = json.load(f)
        
        return sum(1 for site in sites_data.values() if site.get('IP_live_status', False))

