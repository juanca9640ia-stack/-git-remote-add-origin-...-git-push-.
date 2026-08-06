from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from compras.models import Compra, LineaCompra, Proveedor
from inventario.models import Categoria, MovimientoInventario, Producto


class CompraInventarioIntegrationTests(TestCase):
    def setUp(self):
        self.categoria = Categoria.objects.create(nombre="General")
        self.producto = Producto.objects.create(
            sku="SKU-1", nombre="Producto de prueba", categoria=self.categoria,
            precio_costo=Decimal("5.00"), precio_venta=Decimal("10.00"),
            stock_actual=10, stock_minimo=2,
        )
        self.proveedor = Proveedor.objects.create(nombre="Proveedor de prueba")

    def _crear_compra_borrador(self, cantidad):
        compra = Compra.objects.create(proveedor=self.proveedor, impuesto_porcentaje=Decimal("19"))
        LineaCompra.objects.create(compra=compra, producto=self.producto, cantidad=cantidad, precio_unitario=self.producto.precio_costo)
        return compra

    def test_confirmar_compra_aumenta_stock_en_tiempo_real(self):
        compra = self._crear_compra_borrador(cantidad=5)
        compra.confirmar()

        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, 15)
        self.assertEqual(compra.estado, Compra.CONFIRMADA)

        movimiento = MovimientoInventario.objects.latest("id")
        self.assertEqual(movimiento.tipo, MovimientoInventario.ENTRADA)
        self.assertEqual(movimiento.motivo, MovimientoInventario.MOTIVO_COMPRA)
        self.assertEqual(movimiento.cantidad, 5)
        self.assertEqual(movimiento.stock_resultante, 15)

    def test_anular_compra_confirmada_retira_stock(self):
        compra = self._crear_compra_borrador(cantidad=5)
        compra.confirmar()
        compra.anular()

        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, 10)
        self.assertEqual(compra.estado, Compra.ANULADA)

    def test_no_permite_anular_si_ya_no_hay_stock_suficiente(self):
        compra = self._crear_compra_borrador(cantidad=5)
        compra.confirmar()

        # Se vende casi todo el stock recibido antes de intentar anular la compra.
        self.producto.refresh_from_db()
        self.producto.stock_actual = 1
        self.producto.save(update_fields=["stock_actual"])

        with self.assertRaises(ValidationError):
            compra.anular()

        compra.refresh_from_db()
        self.assertEqual(compra.estado, Compra.CONFIRMADA)

    def test_no_permite_confirmar_compra_sin_lineas(self):
        compra = Compra.objects.create(proveedor=self.proveedor)
        with self.assertRaises(ValidationError):
            compra.confirmar()

    def test_calculo_totales_con_impuesto(self):
        compra = self._crear_compra_borrador(cantidad=10)
        self.assertEqual(compra.subtotal, Decimal("50.00"))
        self.assertEqual(compra.impuesto_valor, Decimal("9.50"))
        self.assertEqual(compra.total, Decimal("59.50"))

    def test_confirmar_compra_con_servicio_no_genera_movimiento(self):
        servicio = Producto.objects.create(
            sku="SRV-1", nombre="Asesoría legal", tipo=Producto.SERVICIO,
            categoria=self.categoria, precio_costo=Decimal("100000"),
        )
        compra = Compra.objects.create(proveedor=self.proveedor)
        LineaCompra.objects.create(compra=compra, producto=servicio, cantidad=1, precio_unitario=servicio.precio_costo)

        compra.confirmar()

        servicio.refresh_from_db()
        self.assertEqual(servicio.stock_actual, 0)
        self.assertEqual(compra.estado, Compra.CONFIRMADA)
        self.assertFalse(MovimientoInventario.objects.filter(producto=servicio).exists())


class ProveedorCrearRapidoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="comprador", password="clave-segura-123", email="")
        self.client.force_login(self.user)

    def test_crea_proveedor_con_solo_nombre(self):
        resp = self.client.post(
            "/compras/proveedores/nuevo-rapido/",
            {"nombre": "Proveedor Exprés", "nit": "", "telefono": "", "email": ""},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        proveedor = Proveedor.objects.get(pk=data["id"])
        self.assertEqual(proveedor.nombre, "Proveedor Exprés")
        self.assertTrue(proveedor.activo)

    def test_rechaza_sin_nombre(self):
        resp = self.client.post(
            "/compras/proveedores/nuevo-rapido/",
            {"nombre": "", "nit": "", "telefono": "", "email": ""},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["ok"])
