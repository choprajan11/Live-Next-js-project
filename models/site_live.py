import os
import json
import subprocess
import shutil
from datetime import datetime
import uuid

class SiteLiveManager:
    def __init__(self):
        # Get absolute path for project deployment
        self.PROJECT_DEPLOY_PATH = os.getenv('PROJECT_DEPLOY_PATH', '/root/local_listing_sites')
        self.sites_json_path = os.getenv('SITES_JSON_PATH', 'sites.json')
        self.default_port = int(os.getenv('DEFAULT_PORT', 3000))
        self.server_ip = os.getenv('SERVER_IP', '127.0.0.1')  # ✅ server IP from env
        # Set history directory in current app directory
        self.history_dir = os.path.join(os.getcwd(), 'history')
        os.makedirs(self.history_dir, exist_ok=True)

    def _log_message(self, domain_name, message, status="info"):
        """Log message to file and format for display"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = os.path.join(self.history_dir, f"{domain_name}_local_live_process.log")
        
        # Format the log entry
        if status == "error":
            prefix = "❌ ERROR: "
        elif status == "success":
            prefix = "✅ "
        else:
            prefix = "ℹ️ "
        
        log_entry = f"[{timestamp}] {prefix}{message}\n"
        
        # Write to log file
        with open(log_file, 'a') as f:
            f.write(log_entry)
        
        return {"type": "local", "status": status, "message": message}

    # ✅ Alias to fix your error (_log_command missing)
    def _log_command(self, domain_name, message, status="info"):
        return self._log_message(domain_name, message, status)

    def _run_command(self, command, domain_name, cwd=None):
        """Run a command and wait for completion with real-time output"""
        try:
            # Log command start
            self._log_message(domain_name, f"Running command: {command}")
            
            # Start the command
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=cwd,
                bufsize=1,
                universal_newlines=True
            )
            
            # Monitor output in real-time
            while True:
                # Read output and error streams
                output_line = process.stdout.readline()
                error_line = process.stderr.readline()
                
                # Process stdout
                if output_line:
                    self._log_message(domain_name, output_line.strip())
                
                # Process stderr
                if error_line:
                    self._log_message(domain_name, error_line.strip(), "error")
                
                # Check if process has finished
                if output_line == '' and error_line == '' and process.poll() is not None:
                    break
            
            # Get the final return code
            return_code = process.wait()
            
            # Check final status
            if return_code == 0:
                self._log_message(domain_name, "Command completed successfully", "success")
                return True
            else:
                self._log_message(domain_name, "Command failed", "error")
                return False
                
        except Exception as e:
            # Log any exceptions
            self._log_message(domain_name, f"Error executing command: {str(e)}", "error")
            return False

    def _generate_site_id(self):
        """Generate a unique ID for the site"""
        return str(uuid.uuid4())

    def _get_next_port(self):
        """Get the next available port from sites.json"""
        try:
            if not os.path.exists(self.sites_json_path):
                return self.default_port

            with open(self.sites_json_path, 'r') as f:
                sites_data = json.load(f)
                
            if not sites_data:
                return self.default_port
                
            # Get the highest port number currently in use
            ports = [int(site.get('port', 0)) for site in sites_data.values()]
            return max(ports) + 1 if ports else self.default_port
                
        except (json.JSONDecodeError, FileNotFoundError):
            return self.default_port

    def _update_sites_json(self, site_id, domain_name, port, project_dir):
        """Update the sites.json file with new site information"""
        data = {}
        if os.path.exists(self.sites_json_path):
            try:
                with open(self.sites_json_path, 'r') as f:
                    data = json.load(f)
            except json.JSONDecodeError:
                data = {}

        # Get current timestamp
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ✅ Create site info with real server IP + live status
        site_info = {
            "domain_name": domain_name,
            "port": port,
            "status": "live",
            "IP_URL": f"http://{self.server_ip}:{port}",
            "created_at": current_time,
            "updated_at": current_time,
            "project_dir": project_dir,  # ✅ full absolute path
            "domain_status": False,
            "domain_provider": "namecheap",
            "IP_live_status": True  # ✅ mark live
        }

        # Check if domain already exists
        existing_site_id = None
        for sid, site in data.items():
            if site.get('domain_name') == domain_name:
                existing_site_id = sid
                break

        if existing_site_id:
            # Update existing entry
            data[existing_site_id].update(site_info)
            data[existing_site_id]['created_at'] = data[existing_site_id].get('created_at', current_time)
            data[existing_site_id]['updated_at'] = current_time
            site_id = existing_site_id
        else:
            # Add new entry
            data[site_id] = site_info

        with open(self.sites_json_path, 'w') as f:
            json.dump(data, f, indent=4)

    def deploy_site(self, domain_name, git_url):
        """Deploy a Next.js site using the provided git URL"""
        site_id = self._generate_site_id()
        try:
            # Create base directory if it doesn't exist
            if not os.path.exists(self.PROJECT_DEPLOY_PATH):
                os.makedirs(self.PROJECT_DEPLOY_PATH, exist_ok=True)
                self._log_message(domain_name, f"Created base directory: {self.PROJECT_DEPLOY_PATH}", "success")
            
            # Setup domain directory
            domain_dir = os.path.join(self.PROJECT_DEPLOY_PATH, domain_name)
            
            # Remove existing directory if it exists
            if os.path.exists(domain_dir):
                shutil.rmtree(domain_dir)
                self._log_message(domain_name, f"Removed existing directory: {domain_dir}", "success")
            
            # Create domain directory
            os.makedirs(domain_dir, exist_ok=True)
            self._log_message(domain_name, f"Created domain directory: {domain_dir}", "success")
            
            # Clone the repository
            if not self._run_command(f"git clone {git_url} {domain_dir}", domain_name):
                raise Exception("Failed to clone repository")
            
            # ✅ Save full absolute path instead of repo name
            project_dir = os.path.abspath(domain_dir)
            
            # Install dependencies with memory-saving options
            install_cmd = "npm install --no-audit --no-fund --production=false --prefer-offline"
            if not self._run_command(install_cmd, domain_name, domain_dir):
                # Check if it was a memory issue
                log_file = os.path.join(self.history_dir, f"{domain_name}_local_live_process.log")
                with open(log_file, 'r') as f:
                    last_lines = f.readlines()[-3:]  # Get last 3 lines
                    if any("Killed" in line for line in last_lines):
                        # Try again with additional memory-saving options
                        self._log_message(domain_name, "Retrying npm install with memory-saving options...", "info")
                        install_cmd = "npm install --no-audit --no-fund --production=false --prefer-offline --max-old-space-size=4096 --no-optional"
                        if not self._run_command(install_cmd, domain_name, domain_dir):
                            raise Exception("Failed to install dependencies due to memory constraints. Please free up system memory and try again.")
                    else:
                        raise Exception("Failed to install dependencies")
            
            # Build the project
            if not self._run_command("npm run build", domain_name, domain_dir):
                raise Exception("Failed to build project")
            
            # Get next available port
            port = self._get_next_port()
            
            # Start with PM2
            pm2_prefix = os.getenv('PM2_PREFIX', 'nextjs_site_')
            pm2_cmd = f'pm2 start npm --name "{pm2_prefix}{domain_name}" -- run start -- -p {port}'
            
            if not self._run_command(pm2_cmd, domain_name, domain_dir):
                raise Exception("Failed to start PM2 process")
            
            # Save PM2 configuration
            if not self._run_command("pm2 save", domain_name):
                raise Exception("Failed to save PM2 configuration")
            
            # Update sites.json with absolute path and live status
            self._update_sites_json(site_id, domain_name, port, project_dir)
            
            self._log_message(domain_name, "Site deployed successfully", "success")
            
            return {
                "status": "success",
                "message": "Site deployed successfully",
                "port": port,
                "domain": domain_name,
                "site_id": site_id
            }
            
        except Exception as e:
            error_message = f"Deployment failed: {str(e)}"
            self._log_message(domain_name, error_message, "error")
            return {
                "status": "error",
                "message": error_message,
                "site_id": site_id
            }

    def get_site_status(self, domain_name):
        """Get the current status of a deployed site"""
        try:
            with open(self.sites_json_path, 'r') as f:
                sites_data = json.load(f)
                
            # Search for domain in all entries
            for site_id, site_info in sites_data.items():
                if site_info.get('domain_name') == domain_name:
                    # Get deployment history
                    log_file = os.path.join(self.history_dir, f"{domain_name}_local_live_process.log")
                    deployment_history = []
                    
                    if os.path.exists(log_file):
                        with open(log_file, 'r') as f:
                            deployment_history = f.readlines()
                    
                    site_info['deployment_history'] = deployment_history
                    return site_info
                    
            return {"status": "not_found", "message": f"Site {domain_name} not found"}
            
        except (json.JSONDecodeError, FileNotFoundError):
            return {"status": "error", "message": "Failed to read sites data"}
