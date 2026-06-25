from auth.utils import validate_token


class AuthMiddleware:
    def __call__(self, request):
        return validate_token(request.token)
