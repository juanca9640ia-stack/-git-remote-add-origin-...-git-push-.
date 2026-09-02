from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from core.models import Empresa, PerfilUsuario

from .models import Comunicado


class ComunicadoModelTests(TestCase):
    def test_los_fijados_aparecen_primero(self):
        Comunicado.objects.create(titulo="Normal", cuerpo="...")
        fijado = Comunicado.objects.create(titulo="Fijado", cuerpo="...", fijado=True)
        primero = Comunicado.objects.first()
        self.assertEqual(primero, fijado)


class ComunicadoVistasTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.get(pk=1)

        self.publicador = User.objects.create_user(username="publicador", password="ClaveSegura123")
        PerfilUsuario.objects.create(usuario=self.publicador, empresa=self.empresa)
        self.publicador.user_permissions.add(
            Permission.objects.get(content_type__app_label="comunicaciones", codename="add_comunicado")
        )

        self.lector = User.objects.create_user(username="lector", password="ClaveSegura123")
        PerfilUsuario.objects.create(usuario=self.lector, empresa=self.empresa)

    def test_cualquier_usuario_autenticado_puede_ver_la_lista(self):
        self.client.force_login(self.lector)
        response = self.client.get(reverse("comunicaciones:comunicado_lista"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["puede_publicar"])

    def test_usuario_con_permiso_puede_publicar(self):
        self.client.force_login(self.publicador)
        response = self.client.post(reverse("comunicaciones:comunicado_lista"), {
            "titulo": "Reunión general", "cuerpo": "Viernes a las 3pm.",
        })
        self.assertRedirects(response, reverse("comunicaciones:comunicado_lista"))
        comunicado = Comunicado.objects.get(titulo="Reunión general")
        self.assertEqual(comunicado.publicado_por, self.publicador)
        self.assertEqual(comunicado.empresa, self.empresa)

    def test_usuario_sin_permiso_no_puede_publicar(self):
        self.client.force_login(self.lector)
        response = self.client.post(reverse("comunicaciones:comunicado_lista"), {
            "titulo": "Intento no autorizado", "cuerpo": "...",
        })
        self.assertRedirects(response, reverse("comunicaciones:comunicado_lista"))
        self.assertFalse(Comunicado.objects.filter(titulo="Intento no autorizado").exists())

    def test_autor_puede_eliminar_su_propio_comunicado_aunque_no_tenga_permiso_delete(self):
        comunicado = Comunicado.objects.create(
            empresa=self.empresa, titulo="Mío", cuerpo="...", publicado_por=self.publicador,
        )
        self.client.force_login(self.publicador)
        response = self.client.post(reverse("comunicaciones:comunicado_eliminar", args=[comunicado.pk]))
        self.assertRedirects(response, reverse("comunicaciones:comunicado_lista"))
        self.assertFalse(Comunicado.objects.filter(pk=comunicado.pk).exists())

    def test_usuario_sin_permiso_ni_autoria_no_puede_eliminar(self):
        comunicado = Comunicado.objects.create(
            empresa=self.empresa, titulo="Ajeno", cuerpo="...", publicado_por=self.publicador,
        )
        self.client.force_login(self.lector)
        response = self.client.post(reverse("comunicaciones:comunicado_eliminar", args=[comunicado.pk]))
        self.assertRedirects(response, reverse("comunicaciones:comunicado_lista"))
        self.assertTrue(Comunicado.objects.filter(pk=comunicado.pk).exists())

    def test_lista_solo_muestra_comunicados_de_la_propia_empresa(self):
        otra_empresa = Empresa.objects.create(nombre="Otra constructora")
        Comunicado.objects.create(empresa=self.empresa, titulo="Propio", cuerpo="...")
        Comunicado.objects.create(empresa=otra_empresa, titulo="Ajeno de otra empresa", cuerpo="...")

        self.client.force_login(self.lector)
        response = self.client.get(reverse("comunicaciones:comunicado_lista"))
        titulos = [c.titulo for c in response.context["comunicados"]]
        self.assertIn("Propio", titulos)
        self.assertNotIn("Ajeno de otra empresa", titulos)
