from auth.utils import validate_token


def test_validate_token_returns_payload():
    assert validate_token("abc") is not None
