def disciplinary_status(payload):
    """Only explicit source values substantiate a yes/no disclosure claim."""
    if not isinstance(payload, dict):
        return None
    info = payload.get("basicInformation") or payload
    if not isinstance(info, dict):
        return None
    values = []
    for key in ("hasDisclosure", "hasDrp"):
        value = info.get(key)
        if value is True or value is False:
            values.append(value)
        elif isinstance(value, str):
            if value.lower().strip() in {"true", "yes", "y", "1"}:
                values.append(True)
            elif value.lower().strip() in {"false", "no", "n", "0"}:
                values.append(False)
    # Any explicitly disclosed item takes precedence over a separate false flag.
    return any(values) if values else None
