import os
from command_executor import execute_and_log

def run_deployment_steps(domain_name, git_url):
    """
    Run all deployment steps in sequence and log their outputs
    """
    # Base directory for deployments
    base_dir = os.getenv('PROJECT_DEPLOY_PATH', '/root/local_listing_sites')
    domain_dir = os.path.join(base_dir, domain_name)
    
    # List of commands to execute
    commands = [
        {
            'cmd': f"sudo mkdir -p {domain_dir}",
            'desc': "Creating domain directory",
            'cwd': None
        },
        {
            'cmd': f"git clone {git_url} {domain_dir}",
            'desc': "Cloning repository",
            'cwd': None
        },
        {
            'cmd': "npm install",
            'desc': "Installing dependencies",
            'cwd': domain_dir
        },
        {
            'cmd': "npm run build",
            'desc': "Building project",
            'cwd': domain_dir
        },
        {
            'cmd': f'pm2 start npm --name "nextjs_site_{domain_name}" -- run start -- -p 3000',
            'desc': "Starting PM2 process",
            'cwd': domain_dir
        },
        {
            'cmd': "pm2 save",
            'desc': "Saving PM2 configuration",
            'cwd': domain_dir
        }
    ]
    
    # Execute each command in sequence
    for cmd_info in commands:
        print(f"\nExecuting: {cmd_info['desc']}")
        success = execute_and_log(cmd_info['cmd'], domain_name, cmd_info['cwd'])
        
        if not success:
            print(f"Failed to execute: {cmd_info['desc']}")
            break
        
        print(f"Successfully completed: {cmd_info['desc']}")

if __name__ == "__main__":
    # Example usage
    domain_name = input("Enter domain name: ")
    git_url = input("Enter git repository URL: ")
    run_deployment_steps(domain_name, git_url)
