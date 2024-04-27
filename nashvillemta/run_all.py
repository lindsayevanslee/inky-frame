import subprocess

# List of scripts to run
scripts = ["collect_static_details.py", 
           "collect_vehicles_on_route.py", 
           "find_vehicles_not_yet_passed.py", 
           "calculate_eta.py", 
           "create_board_image.py"]

for script in scripts:
    subprocess.run(["python", script])