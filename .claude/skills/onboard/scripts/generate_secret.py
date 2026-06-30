#!/usr/bin/env python3
"""
generate_secret.py — Generate a random GITHUB_WEBHOOK_SECRET value.
Prints just the value so it can be copy-pasted directly into .env
and into the GitHub webhook configuration.
"""

import secrets

secret = secrets.token_hex(32)
print(secret)
