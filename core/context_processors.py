from .models import Empresa


def empresa(request):
    # request.empresa lo resuelve EmpresaActualMiddleware para usuarios autenticados
    # (la empresa de su perfil, o la que haya elegido si es superadmin de plataforma).
    # En páginas públicas (login) todavía no hay usuario, así que se usa la empresa
    # semilla como respaldo.
    return {"empresa": getattr(request, "empresa", None) or Empresa.get_solo()}


NOMBRES_SECCION = {
    "ventas": "Ventas",
    "compras": "Compras",
    "inventario": "Inventario",
    "finanzas": "Finanzas",
    "produccion": "Producción",
    "rrhh": "RR.HH.",
    "administracion": "Administración",
}

# Casos que no siguen el patrón genérico "_lista/_crear/_editar/_detalle" de abajo.
NOMBRES_PAGINA = {
    "mi_perfil": "Mi perfil",
    "resumen": None,  # la sección ya lo deja claro (Finanzas, RR.HH.)
    "cambiar_empresa": "Cambiar de empresa",
    "empresa_lista": "Empresas de la plataforma",
    "empresa_alta": "Nueva empresa",
    "empresa_editar": "Datos de la empresa",
    "auditoria_lista": "Auditoría",
    "servicio_lista": "Servicios",
}


def breadcrumb(request):
    """Construye 'Inicio / Sección / Página' a partir de la URL actual, sin tener
    que anotar cada una de las plantillas a mano."""
    match = getattr(request, "resolver_match", None)
    app_name = getattr(match, "app_name", None) if match else None
    if not app_name:
        return {}

    seccion = NOMBRES_SECCION.get(app_name, app_name.replace("_", " ").title())
    url_name = match.url_name or ""

    if url_name in NOMBRES_PAGINA:
        pagina = NOMBRES_PAGINA[url_name]
    elif url_name.endswith("_crear") or url_name == "nuevo":
        pagina = "Nuevo"
    elif url_name.endswith("_editar"):
        pagina = "Editar"
    elif url_name.endswith("_detalle"):
        pagina = "Detalle"
    elif url_name.endswith("_form"):
        pagina = "Formulario"
    else:
        pagina = None

    return {"breadcrumb_seccion": seccion, "breadcrumb_pagina": pagina}
