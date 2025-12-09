import os
import json
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, jsonify, url_for, flash
from flask_socketio import SocketIO, emit
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from models.site_live import SiteLiveManager
from models.add_domain import DomainManager
from models.rebuild_site import SiteRebuildManager
from models.bulk_deploy import BulkDeploymentManager

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-here')  # Change this in production
socketio = SocketIO(app)

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per minute"]
)

# API Authentication decorator
def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if api_key and api_key == os.getenv('API_KEY'):
            return f(*args, **kwargs)
        return jsonify({"error": "Invalid or missing API key"}), 401
    return decorated_function

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, username, role):
        self.id = username
        self.role = role

    @staticmethod
    def get(username):
        if os.path.exists('users.json'):
            with open('users.json', 'r') as f:
                users = json.load(f)
                if username in users:
                    return User(username, users[username]['role'])
        return None

@login_manager.user_loader
def load_user(username):
    return User.get(username)

# Initialize managers
site_manager = SiteLiveManager()
domain_manager = DomainManager()
rebuild_manager = SiteRebuildManager()
bulk_manager = BulkDeploymentManager()

# Setup bulk manager callbacks for WebSocket updates
def on_bulk_progress_update(batch_id, progress):
    """Send bulk deployment progress updates through websocket"""
    socketio.emit('bulk_progress_update', {
        'batch_id': batch_id,
        'progress': progress
    })

def on_bulk_log_update(batch_id, log_entry, status, site_name):
    """Send bulk deployment log updates through websocket"""
    socketio.emit('bulk_log_update', {
        'batch_id': batch_id,
        'log_entry': log_entry,
        'status': status,
        'site_name': site_name
    })

bulk_manager.on_progress_update = on_bulk_progress_update
bulk_manager.on_log_update = on_bulk_log_update

def send_log_update(site_id, log_data):
    """Send log updates through websocket"""
    socketio.emit(f'log_update_{site_id}', log_data)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if os.path.exists('users.json'):
            with open('users.json', 'r') as f:
                users = json.load(f)
                if username in users and users[username]['password'] == password:
                    user = User(username, users[username]['role'])
                    login_user(user)
                    next_page = request.args.get('next')
                    return redirect(next_page if next_page else url_for('dashboard'))
        
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route("/", methods=["GET"])
@login_required
def dashboard():
    sites = rebuild_manager.load_sites()
    current_year = datetime.now().year
    return render_template("dashboard.html", sites=sites, current_year=current_year)

@app.route("/site/<site_id>", methods=["GET"])
@login_required
def site_details(site_id):
    # Load sites data from the JSON file
    sites_data = {}
    if os.path.exists(site_manager.sites_json_path):
        try:
            with open(site_manager.sites_json_path, 'r') as f:
                sites_data = json.load(f)
        except json.JSONDecodeError:
            return redirect("/")
    
    # Get the specific site data
    site = sites_data.get(site_id)
    if not site:
        return redirect("/")
    
    # Add the site ID to the site data
    site['id'] = site_id
    
    # Add name if not present (for backward compatibility)
    if 'name' not in site:
        site['name'] = site['domain_name']
    
    current_year = datetime.now().year
    return render_template("site_details.html", site=site, current_year=current_year)

@app.route("/rebuild/<domain_name>", methods=["GET"])
@login_required
def rebuild_site(domain_name):
    print(f"Rebuild route hit for domain: {domain_name}")  # Debug log
    # Load sites data from the JSON file
    sites_data = {}
    if os.path.exists(site_manager.sites_json_path):
        try:
            with open(site_manager.sites_json_path, 'r') as f:
                sites_data = json.load(f)
        except json.JSONDecodeError:
            return redirect("/")
    
    # Find the site with matching domain name
    site_id = None
    site = None
    for sid, s in sites_data.items():
        if s.get('domain_name') == domain_name:
            site_id = sid
            site = s
            break
            
    if not site:
        return redirect("/")
    
    # Add the site ID to the site data
    site['id'] = site_id
    
    # Add name if not present (for backward compatibility)
    if 'name' not in site:
        site['name'] = site['domain_name']
    
    current_year = datetime.now().year
    return render_template("rebuild_site.html", site=site, current_year=current_year)

@app.route("/start-rebuild/<domain_name>", methods=["POST"])
@login_required
def start_rebuild(domain_name):
    try:
        # Load sites data from the JSON file
        sites_data = {}
        if os.path.exists(site_manager.sites_json_path):
            try:
                with open(site_manager.sites_json_path, 'r') as f:
                    sites_data = json.load(f)
            except json.JSONDecodeError:
                return {"status": "error", "message": "Invalid sites data"}, 400

        # Find the site with matching domain name
        site_id = None
        site = None
        for sid, s in sites_data.items():
            if s.get('domain_name') == domain_name:
                site_id = sid
                site = s
                break

        if not site:
            return {"status": "error", "message": "Site not found"}, 404

        if not domain_name:
            return {"status": "error", "message": "Domain name not found for site"}, 400

        # Read existing log file if it exists
        log_file = os.path.join(rebuild_manager.history_dir, f"{domain_name}_rebuild_process.log")
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                send_log_update(site_id, {
                    "type": "rebuild",
                    "status": "info",
                    "message": f.read()
                })

        # Override _log_command to send websocket updates
        original_log_command = rebuild_manager._log_command
        def new_log_command(*args, **kwargs):
            log_data = original_log_command(*args, **kwargs)
            # Modify the log data to indicate it's from rebuild process
            log_data['type'] = 'rebuild'
            send_log_update(site_id, log_data)
            return log_data
        rebuild_manager._log_command = new_log_command

        # Start the rebuild process
        success, message = rebuild_manager.rebuild_site(domain_name, site_id)

        # Restore original _log_command
        rebuild_manager._log_command = original_log_command

        # Always return 200 if the API call completed
        return {
            "status": "success" if success else "error",
            "message": message
        }, 200

    except Exception as e:
        print(f"Error rebuilding site: {str(e)}")
        return {"status": "error", "message": str(e)}, 500

@app.route("/add-site", methods=["POST"])
@login_required
def add_site():
    try:
        data = request.get_json()
        git_link = data["repo"]
        domain_name = data["domain"]
        site_name = data["name"]

        # Get next available port
        port = site_manager._get_next_port()
        
        # Create site info dictionary
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        site_info = {
            "domain_name": domain_name,
            "port": port,
            "status": "pending",
            "IP_URL": f"http://localhost:{port}",
            "created_at": current_time,
            "updated_at": current_time,
            "domain_status": False,
            "domain_provider": "namecheap",
            "IP_live_status": False,
            "repo": git_link,
            "project_dir": ""
        }
        
        # Add site to sites.json using SiteLiveManager's structure
        site_id = site_manager._generate_site_id()
        
        # Load existing data
        sites_data = {}
        if os.path.exists(site_manager.sites_json_path):
            try:
                with open(site_manager.sites_json_path, 'r') as f:
                    sites_data = json.load(f)
            except json.JSONDecodeError:
                sites_data = {}
        
        # Add new site
        sites_data[site_id] = site_info
        
        # Save updated data
        with open(site_manager.sites_json_path, 'w') as f:
            json.dump(sites_data, f, indent=4)
        
        return {"status": "success", "message": "Site added successfully"}, 200
    except Exception as e:
        print(f"Error adding site: {str(e)}")
        return {"status": "error", "message": str(e)}, 400

    current_year = datetime.now().year
    return render_template("dashboard.html", sites=sites, current_year=current_year)

@app.route("/live-local/<site_id>", methods=["POST"])
@login_required
def live_local(site_id):
    try:
        # Load sites data to get site info
        sites_data = {}
        if os.path.exists(site_manager.sites_json_path):
            with open(site_manager.sites_json_path, 'r') as f:
                sites_data = json.load(f)
        
        # Get site info
        site = sites_data.get(site_id)
        if not site:
            return {"status": "error", "message": "Site not found"}, 404
        
        # Read existing log file if it exists
        log_file = os.path.join(site_manager.history_dir, f"{site['domain_name']}_local_live_process.log")
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                send_log_update(site_id, {
                    "type": "local",
                    "status": "info",
                    "message": f.read()
                })
        
        # Override _log_command to send websocket updates
        original_log_command = site_manager._log_command
        def new_log_command(*args, **kwargs):
            log_data = original_log_command(*args, **kwargs)
            send_log_update(site_id, log_data)
            return log_data
        site_manager._log_command = new_log_command
        
        # Deploy site
        result = site_manager.deploy_site(site['domain_name'], site['repo'])
        
        # Restore original _log_command
        site_manager._log_command = original_log_command
        
        # Return result
        if result['status'] == 'success':
            return {"status": "success", "message": "Site deployed locally"}, 200
        else:
            return {"status": "error", "message": result['message']}, 500
            
    except Exception as e:
        print(f"Error deploying site locally: {str(e)}")
        return {"status": "error", "message": str(e)}, 500

@app.route("/add-domain/<site_id>", methods=["POST"])
@login_required
def add_domain(site_id):
    try:
        # Load sites data from the JSON file
        sites_data = {}
        if os.path.exists(site_manager.sites_json_path):
            try:
                with open(site_manager.sites_json_path, 'r') as f:
                    sites_data = json.load(f)
            except json.JSONDecodeError:
                return {"status": "error", "message": "Invalid sites data"}, 400

        # Get the specific site data
        site = sites_data.get(site_id)
        if not site:
            return {"status": "error", "message": "Site not found"}, 404

        # Get the domain name from the site data
        domain_name = site.get('domain_name')
        if not domain_name:
            return {"status": "error", "message": "Domain name not found for site"}, 400

        # Read existing log file if it exists
        log_file = os.path.join(domain_manager.history_dir, f"{domain_name}_domain_live_process.log")
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                send_log_update(site_id, {
                    "type": "domain",
                    "status": "info",
                    "message": f.read()
                })

        # Override _log_command to send websocket updates
        original_log_command = domain_manager._log_command
        def new_log_command(*args, **kwargs):
            log_data = original_log_command(*args, **kwargs)
            # Modify the log data to indicate it's from domain process
            log_data['type'] = 'domain'
            send_log_update(site_id, log_data)
            return log_data
        domain_manager._log_command = new_log_command

        # Setup the domain using DomainManager
        success, message = domain_manager.setup_domain(domain_name, site_id)

        # Restore original _log_command
        domain_manager._log_command = original_log_command

        # Always return 200 if the API call completed
        return {
            "status": "success" if success else "error",
            "message": message
        }, 200

    except Exception as e:
        print(f"Error setting up domain: {str(e)}")
        return {"status": "error", "message": str(e)}, 500

@app.route("/get-domain-logs/<domain_name>")
@login_required
def get_domain_logs(domain_name):
    try:
        log_type = request.args.get('type', 'domain')  # Get log type from query parameter
        if log_type == 'local':
            log_file = os.path.join(site_manager.history_dir, f"{domain_name}_local_live_process.log")
        else:
            log_file = os.path.join(domain_manager.history_dir, f"{domain_name}_domain_live_process.log")
            
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                return {"status": "success", "logs": f.read()}, 200
        return {"status": "error", "message": "Log file not found"}, 404
    except Exception as e:
        print(f"Error reading log file: {str(e)}")
        return {"status": "error", "message": str(e)}, 500

@app.route("/get-rebuild-logs/<domain_name>")
@login_required
def get_rebuild_logs(domain_name):
    try:
        log_file = os.path.join(rebuild_manager.history_dir, f"{domain_name}_rebuild_process.log")
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                return jsonify({
                    "status": "success",
                    "logs": f.read()
                })
        return jsonify({
            "status": "success",
            "logs": ""
        })
    except Exception as e:
        print(f"Error reading rebuild log file: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route("/get-log-content/<domain_name>")
@login_required
def get_log_content(domain_name):
    try:
        log_type = request.args.get('type', 'local')  # Get log type from query parameter
        if log_type == 'domain':
            log_file = os.path.join(domain_manager.history_dir, f"{domain_name}_domain_live_process.log")
        else:
            log_file = os.path.join(site_manager.history_dir, f"{domain_name}_local_live_process.log")
            
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                return f.read()
        return ""
    except Exception as e:
        print(f"Error reading log file: {str(e)}")
        return ""

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

# API Routes (v1)
@app.route("/api/v1/sites", methods=["GET"])
@require_api_key
@limiter.limit("100/minute")
def api_get_sites():
    try:
        sites = rebuild_manager.load_sites()
        return jsonify({"status": "success", "data": sites}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/v1/sites/<site_id>", methods=["GET"])
@require_api_key
@limiter.limit("100/minute")
def api_get_site(site_id):
    try:
        if os.path.exists(site_manager.sites_json_path):
            with open(site_manager.sites_json_path, 'r') as f:
                sites_data = json.load(f)
                site = sites_data.get(site_id)
                if site:
                    site['id'] = site_id
                    return jsonify({"status": "success", "data": site}), 200
                return jsonify({"status": "error", "message": "Site not found"}), 404
        return jsonify({"status": "error", "message": "Sites data not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500



################ Create New Site #################
@app.route("/api/v1/sites", methods=["POST"])
@require_api_key
@limiter.limit("50/minute")
def api_create_site():
    try:
        data = request.get_json()
        required_fields = ["repo", "domain", "name"]
        
        # Validate required fields
        for field in required_fields:
            if field not in data:
                return jsonify({"status": "error", "message": f"Missing required field: {field}"}), 400
                
        # Check if domain already exists
        with open('sites.json', 'r') as f:
            sites = json.load(f)
            
        # Check if domain exists in any site
        for site_id, site_data in sites.items():
            if site_data.get('domain_name') == data['domain']:
                return jsonify({
                    "status": "exists",
                    "message": "Domain already exists",
                    "data": {"site_id": site_id}
                }), 200
        
        # Get next available port
        port = site_manager._get_next_port()
        
        # Create site info
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        site_info = {
            "domain_name": data["domain"],
            "port": port,
            "status": "pending",
            "IP_URL": f"http://localhost:{port}",
            "created_at": current_time,
            "updated_at": current_time,
            "domain_status": False,
            "domain_provider": "namecheap",
            "IP_live_status": False,
            "repo": data["repo"],
            "project_dir": "",
            "name": data["name"]
        }
        
        # Generate site ID and save
        site_id = site_manager._generate_site_id()
        sites_data = {}
        
        if os.path.exists(site_manager.sites_json_path):
            with open(site_manager.sites_json_path, 'r') as f:
                sites_data = json.load(f)
        
        sites_data[site_id] = site_info
        
        with open(site_manager.sites_json_path, 'w') as f:
            json.dump(sites_data, f, indent=4)
        
        return jsonify({
            "status": "success",
            "message": "Site created successfully",
            "data": {"site_id": site_id}
        }), 201
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/v1/sites/<site_id>/deploy", methods=["POST"])
@require_api_key
@limiter.limit("10/minute")
def api_deploy_site(site_id):
    try:
        if not os.path.exists(site_manager.sites_json_path):
            return jsonify({"status": "error", "message": "Sites data not found"}), 404
            
        with open(site_manager.sites_json_path, 'r') as f:
            sites_data = json.load(f)
            site = sites_data.get(site_id)
            
            if not site:
                return jsonify({"status": "error", "message": "Site not found"}), 404
            
            result = site_manager.deploy_site(site['domain_name'], site['repo'])
            return jsonify(result), 200 if result['status'] == 'success' else 500
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/v1/sites/<site_id>/domain", methods=["POST"])
@require_api_key
@limiter.limit("20/minute")
def api_add_domain(site_id):
    try:
        if not os.path.exists(site_manager.sites_json_path):
            return jsonify({"status": "error", "message": "Sites data not found"}), 404
            
        with open(site_manager.sites_json_path, 'r') as f:
            sites_data = json.load(f)
            site = sites_data.get(site_id)
            
            if not site:
                return jsonify({"status": "error", "message": "Site not found"}), 404
            
            r,s = domain_manager.setup_domain(site['domain_name'], site_id)
            return jsonify({"status": "success","message": "Site live successfully"}), 200 if r else 500
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500        


################ Bulk Deployment Routes #################

@app.route("/bulk-deploy", methods=["GET"])
@login_required
def bulk_deploy_page():
    """Bulk deployment dashboard page"""
    # Get counts
    pending_count = bulk_manager.get_pending_sites_count()
    live_count = bulk_manager.get_live_sites_count()
    total_count = pending_count + live_count
    status = bulk_manager.get_status()
    
    return render_template(
        "bulk_deploy.html",
        pending_count=pending_count,
        live_count=live_count,
        total_count=total_count,
        is_running=status['is_running'],
        current_year=datetime.now().year
    )


@app.route("/api/v1/bulk/import", methods=["POST"])
@login_required
def api_bulk_import():
    """Import sites from JSON"""
    try:
        data = request.get_json()
        sites = data.get('sites', [])
        
        if not sites:
            return jsonify({"status": "error", "message": "No sites provided"}), 400
        
        imported, skipped, errors = bulk_manager.import_sites_from_json(sites)
        
        return jsonify({
            "status": "success",
            "imported": imported,
            "skipped": skipped,
            "errors": errors[:10]  # Limit errors returned
        }), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/v1/bulk/export", methods=["GET"])
@login_required
def api_bulk_export():
    """Export sites to JSON"""
    try:
        status_filter = request.args.get('filter', 'all')
        sites = bulk_manager.export_sites_to_json(status_filter)
        
        return jsonify({
            "status": "success",
            "sites": sites
        }), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/v1/bulk/scan-github", methods=["POST"])
@login_required
def api_scan_github():
    """Scan GitHub for Next.js repositories"""
    try:
        data = request.get_json()
        token = data.get('token')
        username = data.get('username')
        org = data.get('org')
        
        if not token:
            return jsonify({"status": "error", "message": "GitHub token required"}), 400
        
        repos = bulk_manager.scan_github_repos(token, username, org)
        
        return jsonify({
            "status": "success",
            "repos": repos,
            "count": len(repos)
        }), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/v1/bulk/deploy", methods=["POST"])
@login_required
def api_bulk_deploy():
    """Start bulk deployment"""
    try:
        data = request.get_json()
        site_ids = data.get('site_ids')
        deploy_local = data.get('deploy_local', True)
        setup_domain = data.get('setup_domain', False)
        status_filter = data.get('status_filter', 'pending')
        max_workers = data.get('max_workers', 3)
        
        # Update max workers
        bulk_manager.max_workers = max_workers
        
        batch_id = bulk_manager.start_bulk_deploy(
            site_ids=site_ids,
            deploy_local=deploy_local,
            setup_domain=setup_domain,
            status_filter=status_filter
        )
        
        return jsonify({
            "status": "success",
            "batch_id": batch_id,
            "message": "Bulk deployment started"
        }), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/v1/bulk/stop", methods=["POST"])
@login_required
def api_bulk_stop():
    """Stop bulk deployment"""
    try:
        stopped = bulk_manager.stop_bulk_deploy()
        
        return jsonify({
            "status": "success" if stopped else "error",
            "message": "Stop requested" if stopped else "No deployment running"
        }), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/v1/bulk/status", methods=["GET"])
@login_required
def api_bulk_status():
    """Get bulk deployment status"""
    try:
        batch_id = request.args.get('batch_id')
        status = bulk_manager.get_status()
        progress = bulk_manager.get_progress(batch_id) if batch_id else {}
        
        return jsonify({
            "status": "success",
            "is_running": status['is_running'],
            "current_batch_id": status['current_batch_id'],
            "progress": progress
        }), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/v1/bulk/logs/<batch_id>", methods=["GET"])
@login_required
def api_bulk_logs(batch_id):
    """Get logs for a bulk deployment batch"""
    try:
        logs = bulk_manager.get_logs(batch_id)
        
        return jsonify({
            "status": "success",
            "logs": logs
        }), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5001, debug=True)