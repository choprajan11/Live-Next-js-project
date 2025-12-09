import os
import json
import subprocess
import shutil
from datetime import datetime
from typing import List, Dict, Tuple

class SiteRebuildManager:
    def __init__(self, data_file: str = None):
        # Use absolute path for data file
        self.data_file = data_file or os.path.join(os.getcwd(), 'sites.json')
        # Ensure history directory exists
        self.history_dir = os.path.join(os.getcwd(), 'history')
        os.makedirs(self.history_dir, exist_ok=True)
        
    def load_sites(self) -> List[Dict]:
        """Load sites from JSON file"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, "r") as f:
                    data = json.load(f)
                    # Convert dictionary to list
                    if isinstance(data, dict):
                        return [
                            {
                                "id": site_id,
                                "name": site_info.get("domain_name", ""),
                                "domain": site_info.get("domain_name", ""),
                                "repo": site_info.get("repo", ""),
                                "project_directory": site_info.get("project_dir", ""),
                                "status": site_info.get("status", "pending"),
                                "time": site_info.get("created_at", ""),
                                "url": site_info.get("api_url", f"http://localhost:{site_info.get('port', '')}"),
                                "local_status": site_info.get("IP_live_status", False),
                                "domain_status": site_info.get("domain_status", False)
                            }
                            for site_id, site_info in data.items()
                        ]
                    return data
        except Exception as e:
            print(f"Error loading sites: {str(e)}")
        return []
    def _log_command(self, domain_name: str, message: str, status: str = "info") -> dict:
        """Log command to file with proper formatting and return log data"""
        return self._log_message(domain_name, message, status)

    def _log_message(self, domain_name: str, message: str, status: str = "info") -> dict:
        """Log message to file with proper formatting and return log data"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_file = os.path.join(self.history_dir, f"{domain_name}_rebuild_process.log")
            print(f"[DEBUG] Writing to log file: {log_file}")
            
            # Format the log entry
            if status == "error":
                prefix = "❌ ERROR: "
            elif status == "success":
                prefix = "✅ "
            else:
                prefix = "ℹ️ "
            
            log_entry = f"[{timestamp}] {prefix}{message}\n"
            
            # Write to log file
            print(f"[DEBUG] Writing log entry: {log_entry}")
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
            print(f"[DEBUG] Successfully wrote to log file")
            
            # Return log data for WebSocket
            return {
                "status": status,
                "message": message,
                "timestamp": timestamp
            }
        except Exception as e:
            print(f"[DEBUG] Error in _log_message: {str(e)}")
            # Still return log data even if file write fails
            return {
                "status": "error",
                "message": f"Error writing to log: {str(e)}",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

    def run_command(self, command: str, cwd: str = None, domain_name: str = None) -> bool:
        """Run a command and wait for completion with real-time output"""
        try:
            # Log command start
            self._log_message(domain_name, f"Running command: {command}")
            if cwd:
                self._log_message(domain_name, f"Working directory: {cwd}")
            
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

    def get_site_info(self, domain_name: str) -> Dict:
        """Get site information from sites.json file"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, "r") as f:
                    data = json.load(f)
                    # Find site info by domain name
                    for site_info in data.values():
                        if site_info.get("domain_name") == domain_name:
                            self._log_message(domain_name, f"Found site information in sites.json", "success")
                            return site_info
            
            self._log_message(domain_name, f"Site information not found for domain: {domain_name}", "error")
        except Exception as e:
            self._log_message(domain_name, f"Error loading site info: {str(e)}", "error")
        return {}

    def test_build(self, domain_name: str) -> Tuple[bool, str]:
        print(f"Starting build test for domain: {domain_name}")
        """
        Test build process for a site
        Returns: (success: bool, logs: str)
        """
        # Clear existing log file and start new log session
        log_file = os.path.join(self.history_dir, f"{domain_name}_rebuild_process.log")
        if os.path.exists(log_file):
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write("")  # Clear the file
        
        # Start new log session
        self._log_message(domain_name, "="*50)
        self._log_message(domain_name, f"Starting build test for domain: {domain_name}")
        self._log_message(domain_name, "="*50)

        # Get site info from sites.json
        site_info = self.get_site_info(domain_name)
        if not site_info:
            return False, f"Site with domain {domain_name} not found in sites.json"

        # Get project directory and repo URL
        project_base_dir = os.path.dirname(site_info.get("project_dir", ""))
        repo_url = site_info.get("repo")

        if not repo_url:
            self._log_message(domain_name, "Repository URL not found", "error")
            return False, f"Repository URL not found for domain {domain_name}"

        # Create _test_build directory
        test_build_dir = os.path.join(project_base_dir, "_test_build")
        
        # Clean up existing test build directory if it exists
        if os.path.exists(test_build_dir):
            try:
                shutil.rmtree(test_build_dir)
                self._log_message(domain_name, "Cleaned up existing test build directory", "success")
            except Exception as e:
                error_msg = f"Failed to clean up test build directory: {str(e)}"
                self._log_message(domain_name, error_msg, "error")
                return False, error_msg

        # Create fresh test build directory
        try:
            os.makedirs(test_build_dir, exist_ok=True)
            self._log_message(domain_name, f"Created test build directory: {test_build_dir}", "success")
        except Exception as e:
            error_msg = f"Failed to create test build directory: {str(e)}"
            self._log_message(domain_name, error_msg, "error")
            return False, error_msg

        # Clone repository
        if not self.run_command(f"git clone {repo_url} .", test_build_dir, domain_name):
            return False, "Failed to clone repository"

        # Install dependencies with memory-saving options
        install_cmd = "npm install --no-audit --no-fund --production=false --prefer-offline"
        if not self.run_command(install_cmd, test_build_dir, domain_name):
            # Check if it was a memory issue
            log_file = os.path.join(self.history_dir, f"{domain_name}_rebuild_process.log")
            with open(log_file, 'r') as f:
                last_lines = f.readlines()[-3:]  # Get last 3 lines
                if any("Killed" in line for line in last_lines):
                    # Try again with additional memory-saving options
                    self._log_message(domain_name, "Retrying npm install with memory-saving options...", "info")
                    install_cmd = "npm install --no-audit --no-fund --production=false --prefer-offline --max-old-space-size=4096 --no-optional"
                    if not self.run_command(install_cmd, test_build_dir, domain_name):
                        return False, "Failed to install dependencies due to memory constraints. Please free up system memory and try again."
                else:
                    return False, "Failed to install dependencies"

        # Run build
        if not self.run_command("npm run build", test_build_dir, domain_name):
            return False, "Build failed"

        self._log_message(domain_name, "Build test completed successfully!", "success")
        self._log_message(domain_name, "="*50)
        
        # If build test is successful, proceed with deployment
        if self.deploy_build(domain_name, test_build_dir, site_info.get("project_dir")):
            return True, "Build test and deployment completed successfully!"
        return False, "Build test succeeded but deployment failed"

    def rebuild_site(self, domain_name: str, site_id: str) -> Tuple[bool, str]:
        """
        Rebuild a site from its repository
        Args:
            domain_name: The domain name of the site
            site_id: The unique identifier of the site
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            self._log_message(domain_name, f"Starting rebuild process for {domain_name}", "info")
            
            # Get site info
            site_info = self.get_site_info(domain_name)
            if not site_info:
                return False, f"Site information not found for {domain_name}"
            
            # Run test build
            success, message = self.test_build(domain_name)
            if not success:
                return False, message
            
            self._log_message(domain_name, "Rebuild completed successfully!", "success")
            return True, "Site rebuilt and deployed successfully"
            
        except Exception as e:
            error_msg = f"Error during rebuild: {str(e)}"
            self._log_message(domain_name, error_msg, "error")
            return False, error_msg

    def deploy_build(self, domain_name: str, test_build_dir: str, project_dir: str) -> bool:
        """
        Deploy the successful test build to the actual project directory
        """
        try:
            self._log_message(domain_name, "Starting deployment process...", "info")
            
            # Delete all content from project directory
            if os.path.exists(project_dir):
                self._log_message(domain_name, f"Cleaning project directory: {project_dir}", "info")
                for item in os.listdir(project_dir):
                    item_path = os.path.join(project_dir, item)
                    try:
                        if os.path.isfile(item_path):
                            os.unlink(item_path)
                        elif os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                    except Exception as e:
                        self._log_message(domain_name, f"Error removing {item_path}: {str(e)}", "error")
                        return False

            # Copy all content from test build directory to project directory
            self._log_message(domain_name, "Copying new build to project directory...", "info")
            for item in os.listdir(test_build_dir):
                source = os.path.join(test_build_dir, item)
                destination = os.path.join(project_dir, item)
                try:
                    if os.path.isdir(source):
                        shutil.copytree(source, destination, dirs_exist_ok=True)
                    else:
                        shutil.copy2(source, destination)
                except Exception as e:
                    self._log_message(domain_name, f"Error copying {item}: {str(e)}", "error")
                    return False

            # Restart the PM2 process
            pm2_command = f"pm2 restart nextjs_site_{domain_name}"
            if not self.run_command(pm2_command, project_dir, domain_name):
                self._log_message(domain_name, "Failed to restart PM2 process", "error")
                return False

            self._log_message(domain_name, "Deployment completed successfully!", "success")
            return True

        except Exception as e:
            self._log_message(domain_name, f"Deployment failed: {str(e)}", "error")
            return False