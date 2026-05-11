from django import template
from decimal import Decimal

register = template.Library()


@register.filter
def currency(value):
    if value is None:
        return '0 сом'
    try:
        num = float(value)
        formatted = f'{num:,.0f}'.replace(',', ' ')
        return f'{formatted} сом'
    except (TypeError, ValueError):
        return str(value)


@register.filter
def abs_value(value):
    try:
        return abs(value)
    except TypeError:
        return value


@register.filter
def deviation_class(value):
    try:
        v = float(value)
        if v > 0:
            return 'text-danger'
        if v < 0:
            return 'text-success'
        return 'text-muted'
    except (TypeError, ValueError):
        return 'text-muted'


@register.filter
def profit_class(value):
    try:
        v = float(value)
        if v >= 0:
            return 'text-success'
        return 'text-danger'
    except (TypeError, ValueError):
        return 'text-muted'


@register.filter
def progress_class(value):
    try:
        v = float(value)
        if v > 100:
            return 'bg-danger'
        if v >= 80:
            return 'bg-warning'
        return 'bg-success'
    except (TypeError, ValueError):
        return 'bg-secondary'


@register.filter
def dict_get(d, key):
    try:
        return d.get(key)
    except AttributeError:
        return None


@register.filter
def enumerate(iterable):
    return list(__builtins__['enumerate'](iterable) if isinstance(__builtins__, dict) else __import__('builtins').enumerate(iterable))


@register.simple_tag
def enumerate_list(iterable):
    return list(__import__('builtins').enumerate(iterable))


@register.filter
def percent(value, total):
    try:
        v = float(value)
        t = float(total)
        if t == 0:
            return 0
        return round(v / t * 100, 1)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0
