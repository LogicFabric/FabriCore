import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend

def generate_vapid_keys():
    # VAPID uses ECDSA P-256 (NIST256p)
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    public_key = private_key.public_key()

    # Get private key in bytes (raw 32 bytes)
    private_bytes = private_key.private_numbers().private_value.to_bytes(32, byteorder='big')
    
    # Get public key in uncompressed form (1 byte 0x04 + 32 bytes X + 32 bytes Y)
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )

    # Web Push requires URL-safe base64 encoding without padding
    private_base64 = base64.urlsafe_b64encode(private_bytes).decode('utf-8').rstrip('=')
    public_base64 = base64.urlsafe_b64encode(public_bytes).decode('utf-8').rstrip('=')

    print(f"VAPID_PRIVATE_KEY={private_base64}")
    print(f"VAPID_PUBLIC_KEY={public_base64}")

if __name__ == "__main__":
    generate_vapid_keys()
