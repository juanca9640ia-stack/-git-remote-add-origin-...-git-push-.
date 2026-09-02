from datetime import date

from django.conf import settings
from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase
from django.urls import reverse

from compras.models import Proveedor
from core.models import Empresa, PerfilUsuario
from inventario.models import Categoria
from proyectos.models import HitoProyecto, Proyecto
from rrhh.models import Departamento
from ventas.models import Cliente


class MultiempresaCimientoTests(TestCase):
    """Fase 0.1: todo modelo de negocio pertenece a una empresa (inquilino), y el
    registro semilla (Inversiones Jasda, pk=1) debe existir siempre tras migrar."""

    def test_empresa_semilla_existe_tras_migrar(self):
        self.assertTrue(Empresa.objects.filter(pk=1).exists())

    def test_registros_nuevos_quedan_en_la_empresa_semilla_por_defecto(self):
        cliente = Cliente.objects.create(nombre="Cliente de prueba")
        proveedor = Proveedor.objects.create(nombre="Proveedor de prueba")
        categoria = Categoria.objects.create(nombre="Categoría de prueba")
        departamento = Departamento.objects.create(nombre="Departamento de prueba")

        for objeto in (cliente, proveedor, categoria, departamento):
            self.assertEqual(objeto.empresa_id, 1)


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

    def test_usuario_sin_permiso_de_dashboard_ve_pantalla_sin_acceso(self):
        self.client.force_login(self.sin_grupo)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/sin_acceso.html")

    def test_usuario_con_permiso_ve_dashboard(self):
        permiso = Permission.objects.get(content_type__app_label="core", codename="ver_dashboard")
        self.vendedor.user_permissions.add(permiso)
        self.client.force_login(self.vendedor)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/dashboard.html")

    def test_usuario_solo_con_marcar_asistencia_es_redirigido_a_mi_perfil(self):
        permiso = Permission.objects.get(content_type__app_label="rrhh", codename="marcar_propia_asistencia")
        self.sin_grupo.user_permissions.add(permiso)
        self.client.force_login(self.sin_grupo)
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, reverse("rrhh:mi_perfil"))


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


class CalendarioTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.get(pk=1)
        self.superuser = User.objects.create_superuser(username="root_cal", password="ClaveSegura123")
        PerfilUsuario.objects.create(usuario=self.superuser, empresa=self.empresa)
        self.client.force_login(self.superuser)

    def test_usuario_sin_permiso_ve_pantalla_de_sin_acceso(self):
        limitado = User.objects.create_user(username="sin_acceso_cal", password="ClaveSegura123")
        PerfilUsuario.objects.create(usuario=limitado, empresa=self.empresa)
        self.client.force_login(limitado)
        response = self.client.get(reverse("calendario"))
        self.assertTemplateUsed(response, "core/sin_acceso.html")

    def test_superusuario_ve_el_calendario(self):
        response = self.client.get(reverse("calendario"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/calendario.html")

    def test_hito_del_mes_aparece_en_el_dia_correcto(self):
        hoy = date.today()
        proyecto = Proyecto.objects.create(empresa=self.empresa, nombre="Obra Calendario")
        hito = HitoProyecto.objects.create(
            empresa=self.empresa, proyecto=proyecto, nombre="Cimentación", fecha_objetivo=hoy,
        )
        response = self.client.get(reverse("calendario"))
        dia_con_eventos = next(
            dia for semana in response.context["semanas"] for dia in semana if dia["fecha"] == hoy
        )
        titulos = [e["titulo"] for e in dia_con_eventos["eventos"]]
        self.assertTrue(any("Cimentación" in t for t in titulos))

    def test_navegar_a_otro_mes_no_falla(self):
        response = self.client.get(reverse("calendario"), {"anio": 2027, "mes": 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["anio"], 2027)
        self.assertEqual(response.context["mes"], 1)
