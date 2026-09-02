from django.contrib import messages
from django.shortcuts import redirect

from core.models import Empresa, PerfilUsuario

# Namespaces de app cuyo acceso exige pertenecer al grupo de permisos del módulo
# (o ser superusuario). El nombre coincide con el app_label de cada app, que es
# justo lo que 'seed_data' usa para filtrar los permisos de cada grupo.
MODULOS_RESTRINGIDOS = {"ventas", "compras", "inventario", "finanzas", "produccion", "rrhh", "proyectos"}


class EmpresaActualMiddleware:
    """Resuelve `request.empresa`: la empresa (inquilino) cuyos datos debe ver este usuario.

    Cada usuario pertenece a una empresa a través de su PerfilUsuario. Un
    superadministrador de la plataforma puede cambiar de empresa activa desde el
    selector del encabezado; esa elección se guarda en la sesión.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.empresa = self._resolver_empresa(request)
        return self.get_response(request)

    def _resolver_empresa(self, request):
        if not request.user.is_authenticated:
            return None

        perfil = getattr(request.user, "perfil", None)
        if perfil is None:
            # Cuenta creada antes de existir el perfil (no debería pasar tras la
            # migración de datos de la Fase 0, pero no debe romper el login).
            perfil, _ = PerfilUsuario.objects.get_or_create(
                usuario=request.user,
                defaults={"empresa_id": 1, "es_superadmin_plataforma": request.user.is_superuser},
            )

        if perfil.es_superadmin_plataforma:
            empresa_id = request.session.get("empresa_activa_id")
            if empresa_id:
                empresa = Empresa.objects.filter(pk=empresa_id).first()
                if empresa:
                    return empresa

        return perfil.empresa


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
