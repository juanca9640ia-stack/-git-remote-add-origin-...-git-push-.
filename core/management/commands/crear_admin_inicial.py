import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Crea un superusuario inicial a partir de las variables de entorno "
        "DJANGO_SUPERUSER_USERNAME / DJANGO_SUPERUSER_EMAIL / DJANGO_SUPERUSER_PASSWORD, "
        "si aún no existe un usuario con ese nombre. Pensado para correr en el build de "
        "producción, donde no hay acceso a una terminal interactiva."
    )

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")

        if not username or not password:
            self.stdout.write("DJANGO_SUPERUSER_USERNAME/PASSWORD no definidos, se omite.")
            return

        User = get_user_model()
        if User.objects.filter(username=username).exists():
            self.stdout.write(f"El usuario '{username}' ya existe, no se modifica.")
            return

        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"Superusuario '{username}' creado."))
