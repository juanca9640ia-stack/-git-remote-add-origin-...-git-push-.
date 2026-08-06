from django.conf import settings
from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase
from django.urls import reverse


class ModuloAccesoMiddlewareTests(TestCase):
    def setUp(self):
        self.grupo_ventas = Group.objects.create(name="Ventas")
        self.grupo_ventas.permissions.set(Permission.objects.filter(content_type__app_label="ventas"))

        self.vendedor = User.objects.create_user(username="vendedor", password="ClaveSegura123")
        self.vendedor.groups.add(self.grupo_ventas)

        self.sin_grupo = User.objects.create_user(username="sinacceso", password="ClaveSegura123")
        self.superuser = User.objects.create_superuser(
            username="root", password="ClaveSegura123", email="root@example.com"
        )

    def test_usuario_con_permiso_accede_a_su_modulo(self):
        self.client.force_login(self.vendedor)
        response = self.client.get(reverse("ventas:venta_lista"))
        self.assertEqual(response.status_code, 200)

    def test_usuario_sin_permiso_es_bloqueado(self):
        self.client.force_login(self.vendedor)
        response = self.client.get(reverse("compras:compra_lista"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard"))

    def test_usuario_sin_ningun_grupo_es_bloqueado(self):
        self.client.force_login(self.sin_grupo)
        response = self.client.get(reverse("ventas:venta_lista"))
        self.assertEqual(response.status_code, 302)

    def test_superusuario_accede_a_todos_los_modulos(self):
        self.client.force_login(self.superuser)
        urls = [
            "ventas:venta_lista", "compras:compra_lista", "inventario:producto_lista",
            "finanzas:resumen", "produccion:orden_lista", "rrhh:resumen",
        ]
        for url_name in urls:
            response = self.client.get(reverse(url_name))
            self.assertEqual(response.status_code, 200, f"{url_name} debería ser accesible para superusuario")

    def test_dashboard_no_esta_restringido(self):
        self.client.force_login(self.sin_grupo)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)


class LoginBruteForceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="protegido", password="ClaveCorrecta123")

    def test_bloquea_login_tras_superar_el_limite_de_intentos(self):
        for _ in range(settings.AXES_FAILURE_LIMIT):
            self.client.post(reverse("login"), {"username": "protegido", "password": "incorrecta"})

        response = self.client.post(
            reverse("login"), {"username": "protegido", "password": "ClaveCorrecta123"}, follow=True,
        )
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_login_correcto_sin_intentos_previos_funciona(self):
        response = self.client.post(
            reverse("login"), {"username": "protegido", "password": "ClaveCorrecta123"}, follow=True,
        )
        self.assertTrue(response.wsgi_request.user.is_authenticated)
