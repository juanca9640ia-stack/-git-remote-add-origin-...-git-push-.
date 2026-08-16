from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect


def permiso_requerido(codename):
    """Exige un permiso puntual (ej. 'rrhh.view_empleado') para entrar a una vista.

    A diferencia de ModuloAccesoMiddleware (que solo exige tener algún permiso en la
    app), esto permite que dos secciones de la misma app queden aisladas entre sí
    (ej. un trabajador con permiso solo para registrar su propia asistencia no debe
    poder ver la nómina, aunque ambas vivan en la app 'rrhh').
    """

    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not request.user.has_perm(codename):
                messages.error(request, "No tienes permiso para acceder a esta sección. Contacta a un administrador.")
                return redirect("dashboard")
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador


def permiso_requerido_alguno(*codenames):
    """Como permiso_requerido, pero exige al menos uno de varios permisos.

    Útil para una pantalla combinada (ej. 'Mi perfil') donde distintas secciones se
    activan con permisos distintos, pero basta con tener cualquiera de ellos para entrar.
    """

    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not any(request.user.has_perm(codename) for codename in codenames):
                messages.error(request, "No tienes permiso para acceder a esta sección. Contacta a un administrador.")
                return redirect("dashboard")
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador
