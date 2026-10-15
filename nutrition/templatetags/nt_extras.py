from django import template

register = template.Library()


@register.filter
def meal_kcal(meal_totals, key):
    """kcal text for one meal section from a {meal_type: Nutrients} dict."""
    n = meal_totals.get(key)
    return f'{n.kcal:.0f} kcal' if n else '0 kcal'
