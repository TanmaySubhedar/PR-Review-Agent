from auth.utils import validate_token


class AdminMiddleware:
    def __call__(self, request):
        return validate_token(request.token)
