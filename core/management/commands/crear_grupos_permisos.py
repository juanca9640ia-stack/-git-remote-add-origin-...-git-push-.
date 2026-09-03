from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

GRUPOS_PERMISOS = {
    "Administración": None,  # todos los permisos
    "Ventas": ["ventas", "bitacora"],
    "Inventario": ["inventario"],
    "Compras": ["compras"],
    "Finanzas": ["finanzas"],
    "Producción": ["produccion"],
    "RR.HH.": ["rrhh"],
    "Proyectos": ["proyectos"],
    "Documentos": ["documentos"],
    "Comunicaciones": ["comunicaciones"],
    "Bitácora": ["bitacora"],
}


class Command(BaseCommand):
    help = "Crea los grupos de permisos por módulo (Administración, Ventas, Inventario, ...)."

    def handle(self, *args, **options):
        admin_group, _ = Group.objects.get_or_create(name="Administración")
        admin_group.permissions.set(Permission.objects.all())

        ver_dashboard = Permission.objects.filter(
            content_type__app_label="core", codename="ver_dashboard"
        ).first()

        for nombre, apps in GRUPOS_PERMISOS.items():
            if apps is None:
                continue
            group, _ = Group.objects.get_or_create(name=nombre)
            permisos = Permission.objects.filter(content_type__app_label__in=apps)
            group.permissions.set(permisos)
            # Los grupos de módulo completo (no granulares) siguen viendo el dashboard,
            # que solo se restringe por defecto para roles creados a mano en Administración > Roles.
            if ver_dashboard:
                group.permissions.add(ver_dashboard)

        self.stdout.write(self.style.SUCCESS(
            "Grupos: Administración, Ventas, Inventario, Compras, Finanzas, Producción, RR.HH., "
            "Proyectos, Documentos, Comunicaciones, Bitácora"
        ))
