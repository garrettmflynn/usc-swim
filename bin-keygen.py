#!/usr/bin/env python3
"""Generate the VAPID keypair that Web Push needs. Run once, keep the output.

  public   -> repository *variable* VAPID_PUBLIC_KEY (goes into the app bundle)
  private  -> repository *secret*   VAPID_PRIVATE_KEY (only the notifier sees it)
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


key = ec.generate_private_key(ec.SECP256R1())
public_numbers = key.public_key().public_numbers()
raw_public = (
    b"\x04"
    + public_numbers.x.to_bytes(32, "big")
    + public_numbers.y.to_bytes(32, "big")
)
raw_private = key.private_numbers().private_value.to_bytes(32, "big")

print("VAPID_PUBLIC_KEY  (repository variable)")
print(f"  {b64(raw_public)}\n")
print("VAPID_PRIVATE_KEY (repository secret)")
print(f"  {b64(raw_private)}\n")
print("Also set VAPID_SUBJECT to mailto:<your address>.")
