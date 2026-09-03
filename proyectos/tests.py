from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from core.models import Empresa, PerfilUsuario
from inventario.models import Categoria, Producto
from rrhh.models import Empleado
from ventas.models import Cliente, CuentaCobro, LineaVenta, Venta

from .models import AsignacionEmpleado, GastoProyecto, HitoProyecto, Proyecto


class ProyectoModelTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(nombre="Constructora Cliente SAS")

    def test_numero_se_autogenera_al_crear(self):
        proyecto = Proyecto.objects.create(nombre="Edificio Norte", presupuesto=Decimal("100000000"))
        self.assertTrue(proyecto.numero.startswith("PROY-"))

    def test_gastado_suma_los_gastos_registrados(self):
        proyecto = Proyecto.objects.create(nombre="Edificio Norte", presupuesto=Decimal("1000000"))
        GastoProyecto.objects.create(proyecto=proyecto, concepto="Cemento", valor=Decimal("300000"))
        GastoProyecto.objects.create(proyecto=proyecto, concepto="Arena", valor=Decimal("200000"))
        self.assertEqual(proyecto.gastado, Decimal("500000"))
        self.assertEqual(proyecto.saldo_presupuesto, Decimal("500000"))
        self.assertEqual(proyecto.porcentaje_gastado, 50)
        self.assertFalse(proyecto.sobre_presupuesto)

    def test_sobre_presupuesto_cuando_el_gasto_supera_lo_aprobado(self):
        proyecto = Proyecto.objects.create(nombre="Edificio Norte", presupuesto=Decimal("100000"))
        GastoProyecto.objects.create(proyecto=proyecto, concepto="Extra", valor=Decimal("150000"))
        self.assertTrue(proyecto.sobre_presupuesto)
        self.assertEqual(proyecto.saldo_presupuesto, Decimal("-50000"))

    def test_gasto_de_valor_cero_o_negativo_no_es_valido(self):
        proyecto = Proyecto.objects.create(nombre="Edificio Norte")
        gasto = GastoProyecto(proyecto=proyecto, concepto="Inválido", valor=Decimal("0"))
        with self.assertRaises(ValidationError):
            gasto.full_clean()

    def test_porcentaje_avance_se_calcula_desde_los_hitos_completados(self):
        proyecto = Proyecto.objects.create(nombre="Edificio Norte")
        h1 = HitoProyecto.objects.create(proyecto=proyecto, nombre="Cimentación")
        HitoProyecto.objects.create(proyecto=proyecto, nombre="Estructura")
        self.assertEqual(proyecto.porcentaje_avance, 0)

        h1.marcar_completado()
        self.assertEqual(proyecto.porcentaje_avance, 50)
        self.assertTrue(h1.completado)

        h1.marcar_pendiente()
        self.assertFalse(h1.completado)
        self.assertIsNone(h1.completado_en)

    def test_proyecto_sin_hitos_tiene_avance_cero(self):
        proyecto = Proyecto.objects.create(nombre="Edificio Sin Hitos")
        self.assertEqual(proyecto.porcentaje_avance, 0)

    def test_ingresos_suma_ventas_confirmadas_y_cuentas_cobro_pagadas_vinculadas(self):
        categoria = Categoria.objects.create(nombre="General")
        producto = Producto.objects.create(
            sku="SKU-1", nombre="Material", categoria=categoria,
            precio_costo=Decimal("5"), precio_venta=Decimal("100000"), stock_actual=50,
        )
        proyecto = Proyecto.objects.create(nombre="Edificio Norte", presupuesto=Decimal("500000"))

        venta = Venta.objects.create(cliente=self.cliente, proyecto=proyecto, impuesto_porcentaje=Decimal("0"))
        LineaVenta.objects.create(venta=venta, producto=producto, cantidad=1, precio_unitario=Decimal("100000"))
        venta.confirmar()  # confirmada -> cuenta

        # una venta en borrador NO debe contar como ingreso todavía
        venta_borrador = Venta.objects.create(cliente=self.cliente, proyecto=proyecto)
        LineaVenta.objects.create(venta=venta_borrador, producto=producto, cantidad=1, precio_unitario=Decimal("50000"))

        cc_pagada = CuentaCobro.objects.create(
            cliente=self.cliente, proyecto=proyecto, concepto="Anticipo", valor=Decimal("200000"),
        )
        cc_pagada.emitir()
        cc_pagada.marcar_pagada()

        # una cuenta de cobro sin pagar tampoco cuenta
        CuentaCobro.objects.create(
            cliente=self.cliente, proyecto=proyecto, concepto="Otra", valor=Decimal("999999"),
        )

        self.assertEqual(proyecto.ingresos, Decimal("300000"))

    def test_utilidad_y_margen_se_calculan_desde_ingresos_y_gastado(self):
        proyecto = Proyecto.objects.create(nombre="Edificio Norte")
        GastoProyecto.objects.create(proyecto=proyecto, concepto="Materiales", valor=Decimal("60000"))
        # Sin ventas/cuentas de cobro pagadas todavía: sin ingresos.
        self.assertEqual(proyecto.ingresos, Decimal("0"))
        self.assertIsNone(proyecto.margen_utilidad)
        self.assertEqual(proyecto.utilidad, Decimal("-60000"))

    def test_hito_vencido_solo_si_no_esta_completado_y_paso_la_fecha(self):
        from datetime import timedelta

        from django.utils import timezone

        proyecto = Proyecto.objects.create(nombre="Edificio Norte")
        hito = HitoProyecto.objects.create(
            proyecto=proyecto, nombre="Entrega", fecha_objetivo=timezone.localdate() - timedelta(days=1)
        )
        self.assertTrue(hito.vencido)
        hito.marcar_completado()
        self.assertFalse(hito.vencido)

    def test_no_se_puede_asignar_dos_veces_el_mismo_empleado_al_mismo_proyecto(self):
        proyecto = Proyecto.objects.create(nombre="Edificio Norte")
        empleado = Empleado.objects.create(nombre_completo="Juan Obrero", documento="123", cargo="Oficial")
        AsignacionEmpleado.objects.create(proyecto=proyecto, empleado=empleado)
        with self.assertRaises(Exception):
            AsignacionEmpleado.objects.create(proyecto=proyecto, empleado=empleado)


class ProyectoVistasTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.get(pk=1)
        self.usuario = User.objects.create_superuser(username="admin_proyectos", password="ClaveSegura123")
        PerfilUsuario.objects.create(usuario=self.usuario, empresa=self.empresa)
        self.client.force_login(self.usuario)
        self.cliente = Cliente.objects.create(empresa=self.empresa, nombre="Constructora Cliente SAS")

    def test_lista_muestra_solo_proyectos_de_la_propia_empresa(self):
        otra_empresa = Empresa.objects.create(nombre="Otra constructora")
        Proyecto.objects.create(empresa=self.empresa, nombre="Obra propia")
        Proyecto.objects.create(empresa=otra_empresa, nombre="Obra ajena")

        response = self.client.get(reverse("proyectos:proyecto_lista"))
        self.assertEqual(response.status_code, 200)
        nombres = [p.nombre for p in response.context["proyectos"]]
        self.assertIn("Obra propia", nombres)
        self.assertNotIn("Obra ajena", nombres)

    def test_crear_proyecto_via_formulario(self):
        response = self.client.post(reverse("proyectos:proyecto_crear"), {
            "nombre": "Torre Residencial", "estado": Proyecto.PLANIFICACION,
            "presupuesto": "500000000", "cliente": self.cliente.pk,
        })
        proyecto = Proyecto.objects.get(nombre="Torre Residencial")
        self.assertRedirects(response, reverse("proyectos:proyecto_detalle", args=[proyecto.pk]))
        self.assertEqual(proyecto.empresa, self.empresa)

    def test_no_puede_ver_el_detalle_de_un_proyecto_de_otra_empresa(self):
        otra_empresa = Empresa.objects.create(nombre="Otra constructora")
        proyecto_ajeno = Proyecto.objects.create(empresa=otra_empresa, nombre="Obra ajena")
        response = self.client.get(reverse("proyectos:proyecto_detalle", args=[proyecto_ajeno.pk]))
        self.assertEqual(response.status_code, 404)

    def test_agregar_hito_desde_el_detalle(self):
        proyecto = Proyecto.objects.create(empresa=self.empresa, nombre="Obra propia")
        response = self.client.post(reverse("proyectos:hito_crear", args=[proyecto.pk]), {
            "nombre": "Cimentación", "orden": 1,
        })
        self.assertRedirects(response, reverse("proyectos:proyecto_detalle", args=[proyecto.pk]))
        self.assertEqual(proyecto.hitos.count(), 1)
        self.assertEqual(proyecto.hitos.first().empresa, self.empresa)

    def test_registrar_gasto_desde_el_detalle(self):
        proyecto = Proyecto.objects.create(empresa=self.empresa, nombre="Obra propia")
        response = self.client.post(reverse("proyectos:gasto_crear", args=[proyecto.pk]), {
            "concepto": "Cemento", "categoria": GastoProyecto.MATERIALES,
            "valor": "250000", "fecha": "2026-01-15",
        })
        self.assertRedirects(response, reverse("proyectos:proyecto_detalle", args=[proyecto.pk]))
        gasto = proyecto.gastos.get()
        self.assertEqual(gasto.valor, Decimal("250000"))
        self.assertEqual(gasto.registrado_por, self.usuario)

    def test_asignar_empleado_con_salario_registra_mano_de_obra_como_gasto(self):
        proyecto = Proyecto.objects.create(empresa=self.empresa, nombre="Obra propia")
        empleado = Empleado.objects.create(
            empresa=self.empresa, nombre_completo="Juan Obrero", documento="123", cargo="Oficial",
            tipo_pago=Empleado.PAGO_SALARIO, salario_base=Decimal("2000000"),
        )
        self.client.post(reverse("proyectos:asignacion_crear", args=[proyecto.pk]), {
            "empleado": empleado.pk, "rol_en_obra": "Maestro de obra",
        })
        gasto = proyecto.gastos.get()
        self.assertEqual(gasto.categoria, GastoProyecto.MANO_OBRA)
        self.assertEqual(gasto.valor, Decimal("2000000"))
        self.assertIn("Juan Obrero", gasto.concepto)
        self.assertEqual(proyecto.gastado, Decimal("2000000"))

    def test_asignar_empleado_por_dia_registra_el_valor_dia_como_gasto(self):
        proyecto = Proyecto.objects.create(empresa=self.empresa, nombre="Obra propia")
        empleado = Empleado.objects.create(
            empresa=self.empresa, nombre_completo="Pedro Ayudante", documento="456", cargo="Ayudante",
            tipo_pago=Empleado.PAGO_DIA, valor_dia=Decimal("80000"),
        )
        self.client.post(reverse("proyectos:asignacion_crear", args=[proyecto.pk]), {
            "empleado": empleado.pk, "rol_en_obra": "",
        })
        gasto = proyecto.gastos.get()
        self.assertEqual(gasto.valor, Decimal("80000"))

    def test_asignar_empleado_sin_valor_de_pago_configurado_no_registra_gasto(self):
        proyecto = Proyecto.objects.create(empresa=self.empresa, nombre="Obra propia")
        empleado = Empleado.objects.create(
            empresa=self.empresa, nombre_completo="Sin Salario", documento="789", cargo="Oficial",
        )
        self.client.post(reverse("proyectos:asignacion_crear", args=[proyecto.pk]), {
            "empleado": empleado.pk, "rol_en_obra": "",
        })
        self.assertEqual(proyecto.gastos.count(), 0)

    def test_asignar_y_retirar_empleado(self):
        proyecto = Proyecto.objects.create(empresa=self.empresa, nombre="Obra propia")
        empleado = Empleado.objects.create(
            empresa=self.empresa, nombre_completo="Juan Obrero", documento="123", cargo="Oficial",
        )
        response = self.client.post(reverse("proyectos:asignacion_crear", args=[proyecto.pk]), {
            "empleado": empleado.pk, "rol_en_obra": "Maestro de obra",
        })
        self.assertRedirects(response, reverse("proyectos:proyecto_detalle", args=[proyecto.pk]))
        asignacion = proyecto.asignaciones.get()
        self.assertTrue(asignacion.activo)

        response = self.client.post(
            reverse("proyectos:asignacion_quitar", args=[proyecto.pk, asignacion.pk])
        )
        self.assertRedirects(response, reverse("proyectos:proyecto_detalle", args=[proyecto.pk]))
        asignacion.refresh_from_db()
        self.assertFalse(asignacion.activo)

    def test_usuario_sin_permiso_de_modulo_no_puede_entrar(self):
        self.client.logout()
        limitado = User.objects.create_user(username="operario_sin_acceso", password="ClaveSegura123")
        PerfilUsuario.objects.create(usuario=limitado, empresa=self.empresa)
        self.client.force_login(limitado)

        response = self.client.get(reverse("proyectos:proyecto_lista"))
        self.assertRedirects(response, reverse("dashboard"))
