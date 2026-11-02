from decimal import Decimal, InvalidOperation
from django import template

register = template.Library()


@register.filter
def research_value(value):
    if value is None:
        return "Unavailable"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            return str(value)
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
    return (
        format(number, ",.2f").rstrip("0").rstrip(".")
        if number != number.to_integral_value()
        else format(number, ",.0f")
    )


@register.filter
def field_label(value):
    return str(value).replace("_", " ").capitalize()
