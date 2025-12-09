import os
import subprocess
import time
from datetime import datetime

def execute_and_log(command, domain_name, working_dir=None):
    """
    Execute a command and log its output to both terminal and file
    """
    # Create domain directory if it doesn't exist
    os.makedirs(domain_name, exist_ok=True)
    
    # Log file path
    log_file = os.path.join(domain_name, 'local_live_process.txt')
    
    # Get timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Prepare log entry header
    log_entry = f"\n{'='*80}\n"
    log_entry += f"Command: {command}\n"
    log_entry += f"Timestamp: {timestamp}\n"
    log_entry += f"Working Directory: {working_dir or os.getcwd()}\n"
    log_entry += f"{'='*80}\n\n"
    
    try:
        # Write command info to log file
        with open(log_file, 'a') as f:
            f.write(log_entry)
        
        # Execute command
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=working_dir,
            bufsize=1,
            universal_newlines=True
        )
        
        # Read and log output in real-time
        while True:
            output_line = process.stdout.readline()
            error_line = process.stderr.readline()
            
            if output_line:
                print(output_line.strip())
                with open(log_file, 'a') as f:
                    f.write(output_line)
            
            if error_line:
                print(error_line.strip())
                with open(log_file, 'a') as f:
                    f.write(f"ERROR: {error_line}")
            
            # Break if process is done and no more output
            if process.poll() is not None and not output_line and not error_line:
                break
        
        # Get final status
        status = "SUCCESS" if process.returncode == 0 else "ERROR"
        
        # Log completion status
        completion_entry = f"\n{'='*80}\n"
        completion_entry += f"Command completed with status: {status}\n"
        completion_entry += f"{'='*80}\n\n"
        
        with open(log_file, 'a') as f:
            f.write(completion_entry)
        
        return process.returncode == 0
        
    except Exception as e:
        error_entry = f"\nERROR: {str(e)}\n"
        with open(log_file, 'a') as f:
            f.write(error_entry)
        return False

if __name__ == "__main__":
    print("This script should be imported and used by other scripts.")
