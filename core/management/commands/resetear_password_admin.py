import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Fuerza la contraseña de DJANGO_SUPERUSER_USERNAME al valor actual de "
        "DJANGO_SUPERUSER_PASSWORD. A diferencia de crear_admin_inicial (que no toca "
        "un usuario que ya existe), este comando SÍ sobrescribe la contraseña; está "
        "pensado para correr una sola vez desde el build cuando no hay Shell disponible "
        "para restablecerla manualmente, y luego quitarse de render.yaml."
    )

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

        if not username or not password:
            self.stdout.write("DJANGO_SUPERUSER_USERNAME/PASSWORD no definidos, se omite.")
            return

        User = get_user_model()
        try:
            usuario = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(f"No existe el usuario '{username}', no hay nada que restablecer.")
            return

        usuario.set_password(password)
        usuario.save(update_fields=["password"])
        self.stdout.write(self.style.SUCCESS(f"Contraseña de '{username}' restablecida."))
