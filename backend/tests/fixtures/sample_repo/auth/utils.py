def decode(token):
    return {"sub": "user", "exp": 0}


def is_expired(payload):
    return False


def validate_token(token):
    payload = decode(token)
    if is_expired(payload):
        return None
    return payload
