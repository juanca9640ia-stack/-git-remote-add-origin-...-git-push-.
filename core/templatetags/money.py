from django import template

register = template.Library()


@register.filter(name="cop")
def cop(value):
    """Formatea un valor monetario sin decimales y con punto de miles. Ej: 1500000 -> $1.500.000"""
    try:
        entero = int(round(float(value)))
    except (TypeError, ValueError):
        return value
    signo = "-" if entero < 0 else ""
    texto = f"{abs(entero):,}".replace(",", ".")
    return f"{signo}${texto}"
