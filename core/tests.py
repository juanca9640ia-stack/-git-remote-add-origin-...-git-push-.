from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from compras.models import Proveedor
from core import analitica
from core.models import Empresa, PerfilUsuario
from inventario.models import Categoria, Producto
from proyectos.models import GastoProyecto, HitoProyecto, Proyecto
from rrhh.models import Departamento
from ventas.models import Cliente, Cotizacion, LineaCotizacion, LineaVenta, Venta


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


class _RequestFake:
    """Doble mínimo de HttpRequest para probar funciones de core.analitica
    que solo necesitan request.empresa y request.user."""

    def __init__(self, empresa, user):
        self.empresa = empresa
        self.user = user


class SaludEmpresarialTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.get(pk=1)
        self.cliente = Cliente.objects.create(nombre="Cliente de prueba", empresa=self.empresa)
        self.categoria = Categoria.objects.create(nombre="General", empresa=self.empresa)
        self.producto = Producto.objects.create(
            sku="SKU-SALUD", nombre="Producto", categoria=self.categoria, empresa=self.empresa,
            precio_costo=Decimal("5"), precio_venta=Decimal("100000"), stock_actual=100,
        )

    def _crear_venta_confirmada(self):
        venta = Venta.objects.create(empresa=self.empresa, cliente=self.cliente)
        LineaVenta.objects.create(
            empresa=self.empresa, venta=venta, producto=self.producto, cantidad=1, precio_unitario=Decimal("100000"),
        )
        venta.confirmar()
        return venta

    def test_sin_datos_suficientes_devuelve_none(self):
        hoy = timezone.localdate()
        self.assertIsNone(analitica.calcular_salud_empresarial(self.empresa, hoy))

    def test_con_datos_suficientes_calcula_score_entre_0_y_100(self):
        hoy = timezone.localdate()
        self._crear_venta_confirmada()
        Cotizacion.objects.create(empresa=self.empresa, cliente=self.cliente)
        Proyecto.objects.create(empresa=self.empresa, nombre="Obra Test", cliente=self.cliente)

        resultado = analitica.calcular_salud_empresarial(self.empresa, hoy)
        self.assertIsNotNone(resultado)
        self.assertTrue(0 <= resultado["score"] <= 100)
        self.assertIn(resultado["estado"], ["Saludable", "Estable", "Requiere atención"])
        self.assertTrue(len(resultado["componentes"]) > 0)

    def test_proyecto_sobre_presupuesto_baja_el_componente_de_proyectos(self):
        hoy = timezone.localdate()
        self._crear_venta_confirmada()
        Cotizacion.objects.create(empresa=self.empresa, cliente=self.cliente)
        proyecto = Proyecto.objects.create(empresa=self.empresa, nombre="Obra en riesgo", presupuesto=Decimal("100"))
        GastoProyecto.objects.create(proyecto=proyecto, concepto="Extra", valor=Decimal("500"))

        resultado = analitica.calcular_salud_empresarial(self.empresa, hoy)
        componente_proyectos = next(c for c in resultado["componentes"] if c["clave"] == "proyectos")
        self.assertEqual(componente_proyectos["tendencia"], "down")


class AlertasYOportunidadesTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.get(pk=1)
        self.user = User.objects.create_superuser(username="analista", password="ClaveSegura123")
        self.request = _RequestFake(self.empresa, self.user)
        self.cliente = Cliente.objects.create(nombre="Cliente Alertas", empresa=self.empresa)
        self.categoria = Categoria.objects.create(nombre="General", empresa=self.empresa)

    def test_factura_vencida_hace_mas_de_30_dias_es_critica(self):
        from finanzas.models import CuentaPorCobrar

        producto = Producto.objects.create(
            sku="SKU-A", nombre="Prod", categoria=self.categoria, empresa=self.empresa,
            precio_costo=Decimal("5"), precio_venta=Decimal("100000"), stock_actual=10,
        )
        venta = Venta.objects.create(empresa=self.empresa, cliente=self.cliente)
        LineaVenta.objects.create(empresa=self.empresa, venta=venta, producto=producto, cantidad=1, precio_unitario=Decimal("100000"))
        venta.confirmar()
        cuenta = CuentaPorCobrar.objects.get(venta=venta)
        cuenta.fecha_vencimiento = timezone.localdate() - timedelta(days=45)
        cuenta.save()

        alertas = analitica.construir_alertas(self.request)
        alerta = next(a for a in alertas if a["titulo"] == "Factura vencida")
        self.assertEqual(alerta["prioridad"], "critica")
        self.assertIn(str(self.cliente), alerta["mensaje"])

    def test_proyecto_en_riesgo_genera_alerta(self):
        proyecto = Proyecto.objects.create(empresa=self.empresa, nombre="Obra riesgo", presupuesto=Decimal("100000"))
        GastoProyecto.objects.create(proyecto=proyecto, concepto="Extra", valor=Decimal("150000"))

        alertas = analitica.construir_alertas(self.request)
        self.assertTrue(any(a["titulo"] == "Proyecto en riesgo" for a in alertas))

    def test_alertas_quedan_ordenadas_de_mas_a_menos_prioritarias(self):
        proyecto = Proyecto.objects.create(empresa=self.empresa, nombre="Obra riesgo", presupuesto=Decimal("100"))
        GastoProyecto.objects.create(proyecto=proyecto, concepto="Extra", valor=Decimal("200"))
        Cotizacion.objects.create(
            empresa=self.empresa, cliente=self.cliente, estado=Cotizacion.ENVIADA,
            fecha_validez=timezone.localdate() - timedelta(days=1),
        )
        alertas = analitica.construir_alertas(self.request)
        pesos = [analitica.PESO_PRIORIDAD[a["prioridad"]] for a in alertas]
        self.assertEqual(pesos, sorted(pesos, reverse=True))

    def test_cotizacion_de_alto_valor_en_negociacion_es_oportunidad(self):
        producto = Producto.objects.create(
            sku="SKU-B", nombre="Prod caro", categoria=self.categoria, empresa=self.empresa,
            precio_costo=Decimal("5"), precio_venta=Decimal("60000000"), stock_actual=10,
        )
        cot = Cotizacion.objects.create(empresa=self.empresa, cliente=self.cliente)
        LineaCotizacion.objects.create(empresa=self.empresa, cotizacion=cot, producto=producto, cantidad=1, precio_unitario=Decimal("60000000"))
        cot.marcar_enviada()

        oportunidades = analitica.detectar_oportunidades(self.request)
        self.assertTrue(any(o["titulo"] == "Cotización de alto valor" for o in oportunidades))

    def test_proyecto_rentable_es_oportunidad(self):
        proyecto = Proyecto.objects.create(empresa=self.empresa, nombre="Obra rentable", cliente=self.cliente)
        producto = Producto.objects.create(
            sku="SKU-C", nombre="Prod", categoria=self.categoria, empresa=self.empresa,
            precio_costo=Decimal("5"), precio_venta=Decimal("1000000"), stock_actual=10,
        )
        venta = Venta.objects.create(empresa=self.empresa, cliente=self.cliente, proyecto=proyecto, impuesto_porcentaje=Decimal("0"))
        LineaVenta.objects.create(empresa=self.empresa, venta=venta, producto=producto, cantidad=1, precio_unitario=Decimal("1000000"))
        venta.confirmar()
        GastoProyecto.objects.create(proyecto=proyecto, concepto="Materiales", valor=Decimal("500000"))  # margen 50%

        oportunidades = analitica.detectar_oportunidades(self.request)
        self.assertTrue(any(o["titulo"] == "Proyecto rentable" for o in oportunidades))

    def test_lo_mas_importante_prioriza_alertas_y_limita_a_5(self):
        alertas = [
            {"prioridad": "critica", "icono": "bi-x", "severidad": "danger", "mensaje": f"A{i}", "url": "#", "accion": "Ver"}
            for i in range(3)
        ]
        oportunidades = [
            {"icono": "bi-y", "mensaje": f"O{i}", "url": "#", "accion": "Ver"} for i in range(4)
        ]
        resultado = analitica.construir_lo_mas_importante(alertas, oportunidades)
        self.assertEqual(len(resultado), 5)
        self.assertTrue(all(r["severidad"] == "danger" for r in resultado[:3]))


class ResumenEjecutivoYActividadTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.get(pk=1)
        self.user = User.objects.create_superuser(username="resumen", password="ClaveSegura123")
        self.request = _RequestFake(self.empresa, self.user)
        self.cliente = Cliente.objects.create(nombre="Cliente Resumen", empresa=self.empresa)
        self.categoria = Categoria.objects.create(nombre="General", empresa=self.empresa)

    def test_resumen_sin_actividad_devuelve_none(self):
        self.assertIsNone(analitica.generar_resumen_ejecutivo(self.request, [], []))

    def test_resumen_con_ventas_genera_texto_con_cifras(self):
        producto = Producto.objects.create(
            sku="SKU-R", nombre="Prod", categoria=self.categoria, empresa=self.empresa,
            precio_costo=Decimal("5"), precio_venta=Decimal("100000"), stock_actual=10,
        )
        venta = Venta.objects.create(empresa=self.empresa, cliente=self.cliente)
        LineaVenta.objects.create(empresa=self.empresa, venta=venta, producto=producto, cantidad=1, precio_unitario=Decimal("100000"))
        venta.confirmar()

        resultado = analitica.generar_resumen_ejecutivo(self.request, [], [])
        self.assertIsNotNone(resultado)
        self.assertIn("$", resultado)

    def test_venta_facturada_aparece_en_actividad_reciente(self):
        producto = Producto.objects.create(
            sku="SKU-T", nombre="Prod", categoria=self.categoria, empresa=self.empresa,
            precio_costo=Decimal("5"), precio_venta=Decimal("100000"), stock_actual=10,
        )
        venta = Venta.objects.create(empresa=self.empresa, cliente=self.cliente)
        LineaVenta.objects.create(empresa=self.empresa, venta=venta, producto=producto, cantidad=1, precio_unitario=Decimal("100000"))
        venta.confirmar()
        venta.facturar("9001")

        eventos = analitica.construir_actividad_reciente(self.request)
        self.assertTrue(any("9001" in e["mensaje"] for e in eventos))


class DashboardCentroDeComandoTests(TestCase):
    """El dashboard ahora es el 'Centro de Comando': verifica que la vista
    exponga toda la nueva jerarquía de información en su contexto."""

    def setUp(self):
        self.user = User.objects.create_superuser(username="gerente_cc", password="ClaveSegura123")
        self.client.force_login(self.user)

    def test_contexto_incluye_las_nuevas_secciones(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        for clave in (
            "salud", "resumen_ejecutivo", "lo_mas_importante", "oportunidades",
            "actividad_reciente", "pipeline", "proyectos_activos", "proyectos_en_riesgo",
        ):
            self.assertIn(clave, response.context)
        self.assertContains(response, "Centro de Comando")

    def test_sin_datos_muestra_mensaje_de_salud_insuficiente(self):
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Estamos recopilando información")
