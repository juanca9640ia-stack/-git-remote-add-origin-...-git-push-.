from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from compras.models import Compra, LineaCompra, Proveedor
from finanzas.models import CuentaPorCobrar, CuentaPorPagar
from inventario.models import Categoria, Producto
from rrhh.models import Departamento, Empleado, Nomina
from ventas.models import Cliente, LineaVenta, Venta


class CuentaPorCobrarIntegrationTests(TestCase):
    def setUp(self):
        categoria = Categoria.objects.create(nombre="General")
        self.producto = Producto.objects.create(
            sku="SKU-1", nombre="Producto de prueba", categoria=categoria,
            precio_costo=Decimal("5.00"), precio_venta=Decimal("10.00"),
            stock_actual=50, stock_minimo=2,
        )
        self.cliente = Cliente.objects.create(nombre="Cliente de prueba")

    def _crear_venta_confirmada(self, cantidad=2):
        # impuesto_porcentaje=0 para que monto_total refleje solo el subtotal en estas pruebas de CxC.
        venta = Venta.objects.create(cliente=self.cliente, impuesto_porcentaje=Decimal("0"))
        LineaVenta.objects.create(venta=venta, producto=self.producto, cantidad=cantidad, precio_unitario=self.producto.precio_venta)
        venta.confirmar()
        return venta

    def test_confirmar_venta_genera_cuenta_por_cobrar_pendiente(self):
        venta = self._crear_venta_confirmada(cantidad=2)
        cuenta = CuentaPorCobrar.objects.get(venta=venta)
        self.assertEqual(cuenta.monto_total, Decimal("20.00"))
        self.assertEqual(cuenta.saldo_pendiente, Decimal("20.00"))
        self.assertEqual(cuenta.estado, CuentaPorCobrar.PENDIENTE)

    def test_registrar_pago_parcial_actualiza_saldo_y_estado(self):
        venta = self._crear_venta_confirmada(cantidad=2)
        cuenta = CuentaPorCobrar.objects.get(venta=venta)

        cuenta.registrar_pago(monto=Decimal("8.00"), metodo="efectivo")
        cuenta.refresh_from_db()
        self.assertEqual(cuenta.saldo_pendiente, Decimal("12.00"))
        self.assertEqual(cuenta.estado, CuentaPorCobrar.PARCIAL)

        cuenta.registrar_pago(monto=Decimal("12.00"), metodo="transferencia")
        cuenta.refresh_from_db()
        self.assertEqual(cuenta.saldo_pendiente, Decimal("0.00"))
        self.assertEqual(cuenta.estado, CuentaPorCobrar.PAGADA)
        self.assertEqual(cuenta.pagos.count(), 2)

    def test_no_permite_pago_mayor_al_saldo_pendiente(self):
        venta = self._crear_venta_confirmada(cantidad=1)
        cuenta = CuentaPorCobrar.objects.get(venta=venta)
        with self.assertRaises(ValidationError):
            cuenta.registrar_pago(monto=Decimal("999.00"), metodo="efectivo")

    def test_anular_venta_sin_pagos_anula_cuenta_por_cobrar(self):
        venta = self._crear_venta_confirmada(cantidad=1)
        venta.anular()
        cuenta = CuentaPorCobrar.objects.get(venta=venta)
        self.assertEqual(cuenta.estado, CuentaPorCobrar.ANULADA)
        self.assertEqual(cuenta.saldo_pendiente, Decimal("0"))

    def test_confirmar_venta_asigna_fecha_vencimiento_a_30_dias(self):
        venta = self._crear_venta_confirmada(cantidad=1)
        cuenta = CuentaPorCobrar.objects.get(venta=venta)
        self.assertEqual(cuenta.fecha_vencimiento, timezone.localdate() + timezone.timedelta(days=30))

    def test_cuenta_vencida_solo_si_paso_fecha_y_sigue_pendiente(self):
        venta = self._crear_venta_confirmada(cantidad=1)
        cuenta = CuentaPorCobrar.objects.get(venta=venta)
        self.assertFalse(cuenta.vencida)

        cuenta.fecha_vencimiento = timezone.localdate() - timezone.timedelta(days=1)
        cuenta.save(update_fields=["fecha_vencimiento"])
        self.assertTrue(cuenta.vencida)

        cuenta.registrar_pago(monto=cuenta.saldo_pendiente, metodo="efectivo")
        cuenta.refresh_from_db()
        self.assertFalse(cuenta.vencida)  # ya pagada, no cuenta como vencida


class CxcListaVistaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="finanzas_user", password="clave-segura-123", email="")
        self.client.force_login(self.user)

        categoria = Categoria.objects.create(nombre="General")
        self.producto = Producto.objects.create(
            sku="SKU-1", nombre="Producto de prueba", categoria=categoria,
            precio_costo=Decimal("5.00"), precio_venta=Decimal("10.00"), stock_actual=50,
        )
        self.cliente_a = Cliente.objects.create(nombre="Cliente A")
        self.cliente_b = Cliente.objects.create(nombre="Cliente B")

        self.venta_a = self._crear_venta_confirmada(self.cliente_a, cantidad=2)
        self.venta_b = self._crear_venta_confirmada(self.cliente_b, cantidad=1)

        cuenta_b = CuentaPorCobrar.objects.get(venta=self.venta_b)
        cuenta_b.fecha_vencimiento = timezone.localdate() - timezone.timedelta(days=5)
        cuenta_b.save(update_fields=["fecha_vencimiento"])

    def _crear_venta_confirmada(self, cliente, cantidad):
        venta = Venta.objects.create(cliente=cliente, impuesto_porcentaje=Decimal("0"))
        LineaVenta.objects.create(venta=venta, producto=self.producto, cantidad=cantidad, precio_unitario=self.producto.precio_venta)
        venta.confirmar()
        return venta

    def test_filtra_por_cliente(self):
        resp = self.client.get(f"/finanzas/cuentas-por-cobrar/?cliente={self.cliente_a.pk}")
        self.assertContains(resp, self.venta_a.numero)
        self.assertNotContains(resp, self.venta_b.numero)

    def test_filtra_solo_vencidas(self):
        resp = self.client.get("/finanzas/cuentas-por-cobrar/?vencidas=1")
        self.assertContains(resp, self.venta_b.numero)
        self.assertNotContains(resp, self.venta_a.numero)

    def test_muestra_saldo_por_cliente(self):
        resp = self.client.get("/finanzas/cuentas-por-cobrar/")
        self.assertContains(resp, "Saldo por cliente")
        self.assertContains(resp, "Cliente A")
        self.assertContains(resp, "Cliente B")


class CuentaPorPagarIntegrationTests(TestCase):
    def setUp(self):
        categoria = Categoria.objects.create(nombre="General")
        self.producto = Producto.objects.create(
            sku="SKU-2", nombre="Insumo de prueba", categoria=categoria,
            precio_costo=Decimal("4.00"), precio_venta=Decimal("9.00"),
            stock_actual=5, stock_minimo=1,
        )
        self.proveedor = Proveedor.objects.create(nombre="Proveedor de prueba")

    def _crear_compra_confirmada(self, cantidad=10):
        compra = Compra.objects.create(proveedor=self.proveedor)
        LineaCompra.objects.create(compra=compra, producto=self.producto, cantidad=cantidad, precio_unitario=self.producto.precio_costo)
        compra.confirmar()
        return compra

    def test_confirmar_compra_genera_cuenta_por_pagar_pendiente(self):
        compra = self._crear_compra_confirmada(cantidad=10)
        cuenta = CuentaPorPagar.objects.get(compra=compra)
        self.assertEqual(cuenta.monto_total, Decimal("40.00"))
        self.assertEqual(cuenta.saldo_pendiente, Decimal("40.00"))
        self.assertEqual(cuenta.estado, CuentaPorPagar.PENDIENTE)

    def test_registrar_pago_a_proveedor(self):
        compra = self._crear_compra_confirmada(cantidad=10)
        cuenta = CuentaPorPagar.objects.get(compra=compra)

        cuenta.registrar_pago(monto=Decimal("40.00"), metodo="transferencia", referencia="TRX-1")
        cuenta.refresh_from_db()
        self.assertEqual(cuenta.saldo_pendiente, Decimal("0.00"))
        self.assertEqual(cuenta.estado, CuentaPorPagar.PAGADA)
        self.assertEqual(cuenta.pagos.first().referencia, "TRX-1")

    def test_origen_y_contraparte_de_cuenta_desde_compra(self):
        compra = self._crear_compra_confirmada(cantidad=10)
        cuenta = CuentaPorPagar.objects.get(compra=compra)
        self.assertEqual(cuenta.origen, compra.numero)
        self.assertEqual(cuenta.contraparte, str(self.proveedor))


class CuentaPorPagarDesdeNominaTests(TestCase):
    def setUp(self):
        departamento = Departamento.objects.create(nombre="Ventas")
        self.empleado = Empleado.objects.create(
            nombre_completo="Laura Gómez", documento="1001", cargo="Vendedora",
            departamento=departamento, salario_base=Decimal("1500000"),
        )

    def _crear_nomina_procesada(self):
        nomina = Nomina.objects.create(periodo="2026-08")
        nomina.generar_detalles()
        nomina.procesar()
        return nomina

    def test_procesar_nomina_genera_cuenta_por_pagar(self):
        nomina = self._crear_nomina_procesada()
        cuenta = CuentaPorPagar.objects.get(nomina=nomina)
        self.assertEqual(cuenta.monto_total, Decimal("1500000"))
        self.assertEqual(cuenta.saldo_pendiente, Decimal("1500000"))
        self.assertEqual(cuenta.estado, CuentaPorPagar.PENDIENTE)
        self.assertIsNone(cuenta.compra)

    def test_origen_y_contraparte_de_cuenta_desde_nomina(self):
        nomina = self._crear_nomina_procesada()
        cuenta = CuentaPorPagar.objects.get(nomina=nomina)
        self.assertEqual(cuenta.origen, "Nómina 2026-08")
        self.assertEqual(cuenta.contraparte, "Nómina de personal")

    def test_registrar_pago_sobre_cuenta_de_nomina(self):
        nomina = self._crear_nomina_procesada()
        cuenta = CuentaPorPagar.objects.get(nomina=nomina)
        cuenta.registrar_pago(monto=Decimal("1500000"), metodo="transferencia")
        cuenta.refresh_from_db()
        self.assertEqual(cuenta.estado, CuentaPorPagar.PAGADA)
        self.assertEqual(cuenta.saldo_pendiente, Decimal("0"))

    def test_guardar_nomina_sin_procesar_no_genera_cuenta(self):
        nomina = Nomina.objects.create(periodo="2026-09")
        nomina.generar_detalles()
        self.assertFalse(CuentaPorPagar.objects.filter(nomina=nomina).exists())
