from werkzeug.security import generate_password_hash
import json

# Generate hashed password
password = "qwety"  # Your desired password
hashed_password = generate_password_hash(password)

# Update users.json with hashed password
users_data = {
    "admin": {
        "password": hashed_password,
        "role": "admin"
    }
}

with open('users.json', 'w') as f:
    json.dump(users_data, f, indent=4)
