_CDN = "https://cdn.akamai.steamstatic.com/steam/apps"


def _validate(app_id: str) -> str:
    s = str(app_id).strip()
    if not s.isdigit():
        raise ValueError(f"app_id must be a digit string, got: {app_id!r}")
    return s


def header_url(app_id: str) -> str:
    return f"{_CDN}/{_validate(app_id)}/header.jpg"


def library_url(app_id: str) -> str:
    return f"{_CDN}/{_validate(app_id)}/library_600x900.jpg"


def capsule_url(app_id: str) -> str:
    return f"{_CDN}/{_validate(app_id)}/capsule_231x87.jpg"
