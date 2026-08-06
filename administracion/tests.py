from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from core.models import Empresa
from finanzas.models import CuentaPorCobrar
from inventario.models import Categoria, MovimientoInventario, Producto
from rrhh.models import Departamento, Empleado, Nomina
from ventas.models import Cliente, LineaVenta, Venta


class UsuarioListaPermisosTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="staff1", password="ClaveSegura123", is_staff=True)
        self.no_staff = User.objects.create_user(username="normal1", password="ClaveSegura123", is_staff=False)

    def test_anonimo_redirige_a_login(self):
        response = self.client.get(reverse("administracion:usuario_lista"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_usuario_sin_staff_no_puede_acceder(self):
        self.client.force_login(self.no_staff)
        response = self.client.get(reverse("administracion:usuario_lista"))
        self.assertEqual(response.status_code, 302)

    def test_staff_puede_ver_lista(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("administracion:usuario_lista"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "normal1")


class UsuarioCrearEditarTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="staff1", password="ClaveSegura123", is_staff=True)
        self.grupo_ventas = Group.objects.create(name="Ventas")
        self.client.force_login(self.staff)

    def test_crear_usuario_con_grupos(self):
        response = self.client.post(reverse("administracion:usuario_crear"), {
            "username": "vendedor1", "first_name": "Ana", "last_name": "Pérez",
            "email": "ana@example.com", "password1": "OtraClave987!", "password2": "OtraClave987!",
            "is_active": "on", "groups": [self.grupo_ventas.pk],
        })
        self.assertEqual(response.status_code, 302)
        usuario = User.objects.get(username="vendedor1")
        self.assertTrue(usuario.check_password("OtraClave987!"))
        self.assertIn(self.grupo_ventas, usuario.groups.all())

    def test_crear_usuario_password_no_coincide(self):
        response = self.client.post(reverse("administracion:usuario_crear"), {
            "username": "vendedor2", "email": "", "password1": "OtraClave987!",
            "password2": "Diferente123!", "is_active": "on",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="vendedor2").exists())

    def test_editar_usuario_actualiza_grupos(self):
        usuario = User.objects.create_user(username="vendedor3", password="ClaveSegura123")
        response = self.client.post(reverse("administracion:usuario_editar", args=[usuario.pk]), {
            "username": "vendedor3", "first_name": "", "last_name": "", "email": "",
            "is_active": "on", "is_staff": "", "groups": [self.grupo_ventas.pk],
        })
        self.assertEqual(response.status_code, 302)
        usuario.refresh_from_db()
        self.assertIn(self.grupo_ventas, usuario.groups.all())

    def test_no_permite_autodesactivarse(self):
        response = self.client.post(reverse("administracion:usuario_editar", args=[self.staff.pk]), {
            "username": "staff1", "first_name": "", "last_name": "", "email": "",
            "is_active": "", "is_staff": "on", "groups": [],
        })
        self.assertEqual(response.status_code, 200)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_active)

    def test_no_permite_quitarse_staff_a_si_mismo(self):
        response = self.client.post(reverse("administracion:usuario_editar", args=[self.staff.pk]), {
            "username": "staff1", "first_name": "", "last_name": "", "email": "",
            "is_active": "on", "is_staff": "", "groups": [],
        })
        self.assertEqual(response.status_code, 200)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_staff)


class UsuarioToggleYPasswordTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="staff1", password="ClaveSegura123", is_staff=True)
        self.otro = User.objects.create_user(username="otro1", password="ClaveSegura123", is_active=True)
        self.client.force_login(self.staff)

    def test_toggle_activo_desactiva_otro_usuario(self):
        response = self.client.post(reverse("administracion:usuario_toggle_activo", args=[self.otro.pk]))
        self.assertEqual(response.status_code, 302)
        self.otro.refresh_from_db()
        self.assertFalse(self.otro.is_active)

    def test_toggle_activo_bloquea_autodesactivacion(self):
        response = self.client.post(reverse("administracion:usuario_toggle_activo", args=[self.staff.pk]))
        self.assertEqual(response.status_code, 302)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_active)

    def test_cambiar_password(self):
        response = self.client.post(reverse("administracion:usuario_cambiar_password", args=[self.otro.pk]), {
            "password1": "NuevaClave456!", "password2": "NuevaClave456!",
        })
        self.assertEqual(response.status_code, 302)
        self.otro.refresh_from_db()
        self.assertTrue(self.otro.check_password("NuevaClave456!"))

    def test_cambiar_password_no_coincide(self):
        response = self.client.post(reverse("administracion:usuario_cambiar_password", args=[self.otro.pk]), {
            "password1": "NuevaClave456!", "password2": "Distinta789!",
        })
        self.assertEqual(response.status_code, 200)
        self.otro.refresh_from_db()
        self.assertFalse(self.otro.check_password("Distinta789!"))


class EmpresaSingletonTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="staff1", password="ClaveSegura123", is_staff=True)
        self.client.force_login(self.staff)

    def test_get_solo_crea_una_unica_fila(self):
        primera = Empresa.get_solo()
        segunda = Empresa.get_solo()
        self.assertEqual(primera.pk, segunda.pk)
        self.assertEqual(Empresa.objects.count(), 1)

    def test_editar_datos_de_la_empresa(self):
        response = self.client.post(reverse("administracion:empresa_editar"), {
            "nombre": "Comercial Andina", "nit": "900123456-1", "direccion": "",
            "telefono": "", "email": "", "moneda": "COP",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Empresa.get_solo().nombre, "Comercial Andina")
        self.assertEqual(Empresa.objects.count(), 1)

    def test_no_staff_no_puede_editar_empresa(self):
        normal = User.objects.create_user(username="normal1", password="ClaveSegura123")
        self.client.logout()
        self.client.force_login(normal)
        response = self.client.get(reverse("administracion:empresa_editar"))
        self.assertEqual(response.status_code, 302)


class AuditoriaTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="staff1", password="ClaveSegura123", is_staff=True)
        self.client.force_login(self.staff)

        categoria = Categoria.objects.create(nombre="General")
        self.producto = Producto.objects.create(
            sku="SKU-1", nombre="Producto", categoria=categoria,
            precio_costo=Decimal("5"), precio_venta=Decimal("10"), stock_actual=50, stock_minimo=2,
        )
        cliente = Cliente.objects.create(nombre="Cliente de prueba")
        venta = Venta.objects.create(cliente=cliente, impuesto_porcentaje=Decimal("0"))
        LineaVenta.objects.create(venta=venta, producto=self.producto, cantidad=1, precio_unitario=Decimal("10"))
        venta.confirmar(usuario=self.staff)

        departamento = Departamento.objects.create(nombre="Ventas")
        empleado = Empleado.objects.create(
            nombre_completo="Laura Gómez", documento="1001", cargo="Vendedora",
            departamento=departamento, salario_base=Decimal("1000000"),
        )
        nomina = Nomina.objects.create(periodo="2026-08")
        nomina.generar_detalles()
        nomina.procesar(usuario=self.staff)
        self.nomina = nomina

    def test_auditoria_requiere_staff(self):
        normal = User.objects.create_user(username="normal1", password="ClaveSegura123")
        self.client.logout()
        self.client.force_login(normal)
        response = self.client.get(reverse("administracion:auditoria_lista"))
        self.assertEqual(response.status_code, 302)

    def test_auditoria_incluye_movimiento_de_inventario(self):
        response = self.client.get(reverse("administracion:auditoria_lista"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SKU-1")

    def test_auditoria_incluye_nomina_procesada_con_usuario(self):
        response = self.client.get(reverse("administracion:auditoria_lista"))
        self.assertContains(response, "Nómina procesada")
        self.assertContains(response, "staff1")
        self.nomina.refresh_from_db()
        self.assertEqual(self.nomina.procesada_por, self.staff)

    def test_pago_registrado_aparece_en_auditoria(self):
        cuenta = CuentaPorCobrar.objects.first()
        cuenta.registrar_pago(monto=Decimal("10"), metodo="efectivo", usuario=self.staff)
        response = self.client.get(reverse("administracion:auditoria_lista"))
        self.assertContains(response, "Pago recibido de cliente")


class RolTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="staff_rol", password="ClaveSegura123", is_staff=True)
        self.client.force_login(self.staff)

    def test_crear_rol_asigna_permisos_de_los_modulos_elegidos(self):
        response = self.client.post(reverse("administracion:rol_crear"), {
            "nombre": "Vendedor junior", "ventas": "on", "inventario": "on",
        })
        self.assertRedirects(response, reverse("administracion:rol_lista"))

        grupo = Group.objects.get(name="Vendedor junior")
        app_labels = set(grupo.permissions.values_list("content_type__app_label", flat=True))
        self.assertEqual(app_labels, {"ventas", "inventario"})

    def test_rechaza_nombre_duplicado(self):
        Group.objects.create(name="Cajero")
        response = self.client.post(reverse("administracion:rol_crear"), {"nombre": "Cajero"})
        self.assertContains(response, "Ya existe un rol con ese nombre")
        self.assertEqual(Group.objects.filter(name="Cajero").count(), 1)

    def test_editar_rol_actualiza_modulos(self):
        grupo = Group.objects.create(name="Cajero")
        response = self.client.post(reverse("administracion:rol_editar", args=[grupo.pk]), {
            "nombre": "Cajero", "finanzas": "on",
        })
        self.assertRedirects(response, reverse("administracion:rol_lista"))
        grupo.refresh_from_db()
        app_labels = set(grupo.permissions.values_list("content_type__app_label", flat=True))
        self.assertEqual(app_labels, {"finanzas"})

    def test_eliminar_rol(self):
        grupo = Group.objects.create(name="Temporal")
        self.client.post(reverse("administracion:rol_eliminar", args=[grupo.pk]))
        self.assertFalse(Group.objects.filter(pk=grupo.pk).exists())

    def test_usuario_sin_staff_no_puede_gestionar_roles(self):
        self.client.logout()
        normal = User.objects.create_user(username="normal_rol", password="ClaveSegura123", is_staff=False)
        self.client.force_login(normal)
        response = self.client.get(reverse("administracion:rol_lista"))
        self.assertEqual(response.status_code, 302)
