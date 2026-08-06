from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

GRUPOS_PERMISOS = {
    "Administración": None,  # todos los permisos
    "Ventas": ["ventas"],
    "Inventario": ["inventario"],
    "Compras": ["compras"],
    "Finanzas": ["finanzas"],
    "Producción": ["produccion"],
    "RR.HH.": ["rrhh"],
}


class Command(BaseCommand):
    help = "Crea los grupos de permisos por módulo (Administración, Ventas, Inventario, ...)."

    def handle(self, *args, **options):
        admin_group, _ = Group.objects.get_or_create(name="Administración")
        admin_group.permissions.set(Permission.objects.all())

        for nombre, apps in GRUPOS_PERMISOS.items():
            if apps is None:
                continue
            group, _ = Group.objects.get_or_create(name=nombre)
            permisos = Permission.objects.filter(content_type__app_label__in=apps)
            group.permissions.set(permisos)

        self.stdout.write(self.style.SUCCESS(
            "Grupos: Administración, Ventas, Inventario, Compras, Finanzas, Producción, RR.HH."
        ))
