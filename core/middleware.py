from django.contrib import messages
from django.shortcuts import redirect

# Namespaces de app cuyo acceso exige pertenecer al grupo de permisos del módulo
# (o ser superusuario). El nombre coincide con el app_label de cada app, que es
# justo lo que 'seed_data' usa para filtrar los permisos de cada grupo.
MODULOS_RESTRINGIDOS = {"ventas", "compras", "inventario", "finanzas", "produccion", "rrhh"}


class ModuloAccesoMiddleware:
    """Bloquea el acceso a un módulo si el usuario no tiene ningún permiso sobre esa app.

    Los grupos de permisos (Ventas, Compras, Inventario, Finanzas, Producción, RR.HH.,
    Administración) ya existen vía 'seed_data', pero por sí solos no restringen nada:
    Django solo los aplica si algo los consulta. Este middleware es ese "algo",
    centralizado en un único lugar en vez de decorar cada vista de cada app.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated:
            return None

        match = request.resolver_match
        app_name = match.app_name if match else None
        if app_name not in MODULOS_RESTRINGIDOS:
            return None

        if request.user.has_module_perms(app_name):
            return None

        messages.error(request, "No tienes permiso para acceder a este módulo. Contacta a un administrador.")
        return redirect("dashboard")
