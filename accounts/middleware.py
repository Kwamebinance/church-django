"""
Loads the current user's Profile once per request and attaches it to the request,
so views and the (coming) permission layer never re-query it. Mirrors the
blueprint's CurrentContextMiddleware.
"""
from .models import Profile


class CurrentContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.profile = None
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            request.profile = (
                Profile.objects
                .select_related("member", "church")
                .filter(user_id=user.id)
                .first()
            )
        return self.get_response(request)
