def readable(value):
    """Normalize double-escaped line breaks in model prose, without decoding Unicode."""
    return str(value or '').replace('\\r\\n','\n').replace('\\n','\n').replace('\\t','    ').strip()
