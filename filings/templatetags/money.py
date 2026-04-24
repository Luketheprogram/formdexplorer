from django import template

register = template.Library()


@register.filter(name="dollars")
def dollars(value):
    """Compact-abbreviate a dollar amount: 50000000 -> $50M, 1250000000 -> $1.25B."""
    if value in (None, ""):
        return "—"
    try:
        v = int(value)
    except (TypeError, ValueError):
        return "—"
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1_000_000_000:
        return f"{sign}${v / 1_000_000_000:.2f}B".replace(".00B", "B")
    if v >= 1_000_000:
        return f"{sign}${v / 1_000_000:.1f}M".replace(".0M", "M")
    if v >= 1_000:
        return f"{sign}${v / 1_000:.1f}K".replace(".0K", "K")
    return f"{sign}${v}"


@register.filter(name="dollars_full")
def dollars_full(value):
    """Full-comma dollar amount: 50000000 -> $50,000,000."""
    if value in (None, ""):
        return "—"
    try:
        v = int(value)
    except (TypeError, ValueError):
        return "—"
    return f"${v:,}"
