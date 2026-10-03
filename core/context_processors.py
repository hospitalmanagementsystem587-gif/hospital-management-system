def staff_roles(request):
    if not request.user.is_authenticated:
        return {}
    roles = set(request.user.groups.values_list("name", flat=True))
    return {
        "is_reception": "Reception" in roles,
        "is_pharmacy": "Pharmacy" in roles,
        "is_doctor": "Doctor" in roles,
        "is_administrator": "Administrator" in roles,
    }
