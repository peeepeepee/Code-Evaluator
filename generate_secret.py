import secrets

# Generate a 32-byte (256-bit) random secret key and convert to hex
secret_key = secrets.token_hex(32)
print(f"Generated SECRET_KEY: {secret_key}")