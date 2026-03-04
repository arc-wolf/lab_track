from django.utils.cache import patch_cache_control


class NoStoreForAuthenticatedPagesMiddleware:
    """
    Prevent browser/proxy caching of authenticated HTML responses so that
    browser "Back" after logout does not display stale private pages.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if (
            getattr(request, "user", None)
            and request.user.is_authenticated
            and request.method == "GET"
            and response.get("Content-Type", "").startswith("text/html")
        ):
            patch_cache_control(
                response,
                no_cache=True,
                no_store=True,
                must_revalidate=True,
                private=True,
            )
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"

        return response
