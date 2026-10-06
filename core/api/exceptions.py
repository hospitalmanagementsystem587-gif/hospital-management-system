from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        custom_data = {
            "error": {
                "status_code": response.status_code,
                "message": (
                    response.data.get("detail", "Request failed")
                    if isinstance(response.data, dict)
                    else "Request failed"
                ),
                "details": response.data,
            }
        }
        response.data = custom_data

    return response
