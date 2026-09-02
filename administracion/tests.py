from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from core.models import Empresa, GrupoEmpresa, PerfilUsuario
from finanzas.models import CuentaPorCobrar
from inventario.models import Categoria, MovimientoInventario, Producto
from rrhh.models import Departamento, Empleado, Nomina
from ventas.models import Cliente, LineaVenta, Venta


class UsuarioListaPermisosTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="staff1", password="ClaveSegura123", is_staff=True)
        self.no_staff = User.objects.create_user(username="normal1", password="ClaveSegura123", is_staff=False)
        PerfilUsuario.objects.create(usuario=self.staff, empresa_id=1)
        PerfilUsuario.objects.create(usuario=self.no_staff, empresa_id=1)

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
        PerfilUsuario.objects.create(usuario=usuario, empresa_id=1)
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
        PerfilUsuario.objects.create(usuario=self.otro, empresa_id=1)
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
        GrupoEmpresa.objects.create(grupo=grupo, empresa_id=1)
        response = self.client.post(reverse("administracion:rol_editar", args=[grupo.pk]), {
            "nombre": "Cajero", "finanzas": "on",
        })
        self.assertRedirects(response, reverse("administracion:rol_lista"))
        grupo.refresh_from_db()
        app_labels = set(grupo.permissions.values_list("content_type__app_label", flat=True))
        self.assertEqual(app_labels, {"finanzas"})

    def test_eliminar_rol(self):
        grupo = Group.objects.create(name="Temporal")
        GrupoEmpresa.objects.create(grupo=grupo, empresa_id=1)
        self.client.post(reverse("administracion:rol_eliminar", args=[grupo.pk]))
        self.assertFalse(Group.objects.filter(pk=grupo.pk).exists())

    def test_no_puede_editar_ni_eliminar_un_rol_compartido_de_plataforma(self):
        grupo = Group.objects.create(name="Compartido de prueba")
        response = self.client.get(reverse("administracion:rol_editar", args=[grupo.pk]))
        self.assertEqual(response.status_code, 404)
        response = self.client.post(reverse("administracion:rol_eliminar", args=[grupo.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Group.objects.filter(pk=grupo.pk).exists())

    def test_usuario_sin_staff_no_puede_gestionar_roles(self):
        self.client.logout()
        normal = User.objects.create_user(username="normal_rol", password="ClaveSegura123", is_staff=False)
        self.client.force_login(normal)
        response = self.client.get(reverse("administracion:rol_lista"))
        self.assertEqual(response.status_code, 302)

    def test_apartado_operario_otorga_solo_los_permisos_de_autoservicio(self):
        response = self.client.post(reverse("administracion:rol_crear"), {
            "nombre": "Trabajador de campo", "rrhh_operario": "on",
        })
        self.assertRedirects(response, reverse("administracion:rol_lista"))

        grupo = Group.objects.get(name="Trabajador de campo")
        codenames = set(grupo.permissions.values_list("codename", flat=True))
        self.assertEqual(codenames, {"marcar_propia_asistencia", "ver_propio_perfil"})

    def test_apartado_rrhh_empleados_no_incluye_nomina_ni_prestamos(self):
        response = self.client.post(reverse("administracion:rol_crear"), {
            "nombre": "RRHH junior", "rrhh_empleados": "on",
        })
        self.assertRedirects(response, reverse("administracion:rol_lista"))

        grupo = Group.objects.get(name="RRHH junior")
        modelos = set(grupo.permissions.values_list("content_type__model", flat=True))
        self.assertEqual(modelos, {"empleado", "departamento"})


class CambiarEmpresaTests(TestCase):
    def setUp(self):
        self.empresa_b = Empresa.objects.create(nombre="Constructora Vecina S.A.S")
        self.superadmin = User.objects.create_user(username="super1", password="ClaveSegura123")
        PerfilUsuario.objects.create(usuario=self.superadmin, empresa_id=1, es_superadmin_plataforma=True)
        self.normal = User.objects.create_user(username="normal_empresa", password="ClaveSegura123")
        PerfilUsuario.objects.create(usuario=self.normal, empresa_id=1, es_superadmin_plataforma=False)

    def test_usuario_normal_no_puede_cambiar_de_empresa(self):
        self.client.force_login(self.normal)
        response = self.client.get(reverse("administracion:cambiar_empresa"))
        self.assertRedirects(response, reverse("dashboard"))

    def test_superadmin_puede_cambiar_la_empresa_activa(self):
        self.client.force_login(self.superadmin)
        response = self.client.post(reverse("administracion:cambiar_empresa"), {"empresa_id": self.empresa_b.pk})
        self.assertRedirects(response, reverse("dashboard"))
        self.assertEqual(self.client.session["empresa_activa_id"], self.empresa_b.pk)


class AislamientoMultiempresaTests(TestCase):
    """Fase 0.4: un usuario de una empresa nunca debe ver ni poder tocar los datos de otra."""

    def setUp(self):
        self.empresa_a = Empresa.objects.get(pk=1)
        self.empresa_b = Empresa.objects.create(nombre="Constructora Vecina S.A.S")

        self.usuario_a = User.objects.create_superuser(username="admin_a", password="ClaveSegura123")
        PerfilUsuario.objects.create(usuario=self.usuario_a, empresa=self.empresa_a)
        self.usuario_b = User.objects.create_superuser(username="admin_b", password="ClaveSegura123")
        PerfilUsuario.objects.create(usuario=self.usuario_b, empresa=self.empresa_b)

        self.cliente_a = Cliente.objects.create(empresa=self.empresa_a, nombre="Cliente de A")
        self.cliente_b = Cliente.objects.create(empresa=self.empresa_b, nombre="Cliente de B")

        self.producto_a = Producto.objects.create(
            empresa=self.empresa_a, sku="SKU-1", nombre="Producto de A", precio_venta=Decimal("10"),
        )
        self.producto_b = Producto.objects.create(
            empresa=self.empresa_b, sku="SKU-1", nombre="Producto de B", precio_venta=Decimal("20"),
        )

        self.empleado_a = Empleado.objects.create(
            empresa=self.empresa_a, nombre_completo="Empleado de A", documento="1", cargo="Obrero", telefono="1",
        )
        self.empleado_b = Empleado.objects.create(
            empresa=self.empresa_b, nombre_completo="Empleado de B", documento="1", cargo="Obrero", telefono="1",
        )

        venta_a = Venta.objects.create(empresa=self.empresa_a, cliente=self.cliente_a)
        LineaVenta.objects.create(
            empresa=self.empresa_a, venta=venta_a, producto=self.producto_a, cantidad=1, precio_unitario=10,
        )
        self.venta_a = venta_a

    def test_mismo_sku_en_dos_empresas_no_choca(self):
        # Ambos productos usan "SKU-1" — solo es posible porque la unicidad es por empresa.
        self.assertEqual(Producto.objects.filter(sku="SKU-1").count(), 2)

    def test_mismo_documento_de_empleado_en_dos_empresas_no_choca(self):
        self.assertEqual(Empleado.objects.filter(documento="1").count(), 2)

    def test_lista_de_clientes_no_mezcla_empresas(self):
        self.client.force_login(self.usuario_a)
        response = self.client.get(reverse("ventas:cliente_lista"))
        self.assertContains(response, "Cliente de A")
        self.assertNotContains(response, "Cliente de B")

    def test_no_se_puede_abrir_un_cliente_de_otra_empresa_por_url_directa(self):
        self.client.force_login(self.usuario_a)
        response = self.client.get(reverse("ventas:cliente_editar", args=[self.cliente_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_no_se_puede_abrir_una_venta_de_otra_empresa_por_url_directa(self):
        self.client.force_login(self.usuario_b)
        response = self.client.get(reverse("ventas:venta_detalle", args=[self.venta_a.pk]))
        self.assertEqual(response.status_code, 404)

    def test_no_se_puede_abrir_un_empleado_de_otra_empresa_por_url_directa(self):
        self.client.force_login(self.usuario_a)
        response = self.client.get(reverse("rrhh:empleado_detalle", args=[self.empleado_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_dashboard_solo_cuenta_los_productos_de_su_propia_empresa(self):
        self.client.force_login(self.usuario_a)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["total_productos"], 1)

    def test_lista_de_usuarios_no_mezcla_empresas(self):
        self.client.force_login(self.usuario_a)
        response = self.client.get(reverse("administracion:usuario_lista"))
        self.assertContains(response, "admin_a")
        self.assertNotContains(response, "admin_b")

    def test_no_se_puede_editar_un_usuario_de_otra_empresa_por_url_directa(self):
        self.client.force_login(self.usuario_a)
        response = self.client.get(reverse("administracion:usuario_editar", args=[self.usuario_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_producto_form_de_a_no_ofrece_clientes_ni_productos_de_b(self):
        self.client.force_login(self.usuario_a)
        response = self.client.get(reverse("ventas:venta_crear"))
        self.assertContains(response, "Cliente de A")
        self.assertNotContains(response, "Cliente de B")
