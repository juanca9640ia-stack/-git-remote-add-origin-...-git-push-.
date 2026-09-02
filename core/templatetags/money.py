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


_UNIDADES = [
    "cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez",
    "once", "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte",
]
_DECENAS = ["", "", "veinte", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa"]
_CENTENAS = [
    "", "ciento", "doscientos", "trescientos", "cuatrocientos", "quinientos",
    "seiscientos", "setecientos", "ochocientos", "novecientos",
]
_VEINTIS = {
    1: "veintiuno", 2: "veintidós", 3: "veintitrés", 4: "veinticuatro", 5: "veinticinco",
    6: "veintiséis", 7: "veintisiete", 8: "veintiocho", 9: "veintinueve",
}


def _tres_digitos(n):
    if n == 0:
        return ""
    if n == 100:
        return "cien"
    centena, resto = divmod(n, 100)
    partes = []
    if centena:
        partes.append(_CENTENAS[centena])
    if resto:
        if resto <= 20:
            partes.append(_UNIDADES[resto])
        else:
            decena, unidad = divmod(resto, 10)
            if decena == 2 and unidad:
                partes.append(_VEINTIS[unidad])
            elif unidad:
                partes.append(f"{_DECENAS[decena]} y {_UNIDADES[unidad]}")
            else:
                partes.append(_DECENAS[decena])
    return " ".join(partes)


def _numero_a_letras(n):
    n = int(n)
    if n == 0:
        return "cero"
    signo = "menos " if n < 0 else ""
    n = abs(n)

    millones, resto = divmod(n, 1_000_000)
    miles, cientos = divmod(resto, 1000)

    partes = []
    if millones:
        partes.append("un millón" if millones == 1 else f"{_tres_digitos(millones)} millones")
    if miles:
        partes.append("mil" if miles == 1 else f"{_tres_digitos(miles)} mil")
    if cientos:
        partes.append(_tres_digitos(cientos))
    return signo + " ".join(partes)


@register.filter(name="en_letras")
def en_letras(value):
    """Convierte un valor monetario a letras, en mayúsculas, para cuentas de cobro. Ej: 150000 -> CIENTO CINCUENTA MIL PESOS M/CTE"""
    try:
        entero = int(round(float(value)))
    except (TypeError, ValueError):
        return value
    return f"{_numero_a_letras(entero).upper()} PESOS M/CTE"
