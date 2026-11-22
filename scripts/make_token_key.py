"""Prints a random key for the TOKEN_KEY secret (encrypts rotating tokens saved in state/)."""
from cryptography.fernet import Fernet
print("TOKEN_KEY =", Fernet.generate_key().decode())
