from .models import Empresa


def empresa(request):
    # request.empresa lo resuelve EmpresaActualMiddleware para usuarios autenticados
    # (la empresa de su perfil, o la que haya elegido si es superadmin de plataforma).
    # En páginas públicas (login) todavía no hay usuario, así que se usa la empresa
    # semilla como respaldo.
    return {"empresa": getattr(request, "empresa", None) or Empresa.get_solo()}
