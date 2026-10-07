from django.http import HttpResponse


def portal_home(request):
    """Minimal boundary marker; portal features are implemented by later tickets."""
    return HttpResponse(f"{request.portal.title()} portal")
