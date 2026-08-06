from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from inventario.models import Categoria, MovimientoInventario, Producto
from ventas.models import Cliente, Cotizacion, LineaCotizacion, LineaVenta, Venta


class VentaInventarioIntegrationTests(TestCase):
    def setUp(self):
        self.categoria = Categoria.objects.create(nombre="General")
        self.producto = Producto.objects.create(
            sku="SKU-1", nombre="Producto de prueba", categoria=self.categoria,
            precio_costo=Decimal("5.00"), precio_venta=Decimal("10.00"),
            stock_actual=10, stock_minimo=2,
        )
        self.cliente = Cliente.objects.create(nombre="Cliente de prueba")

    def _crear_venta_borrador(self, cantidad):
        venta = Venta.objects.create(cliente=self.cliente, impuesto_porcentaje=Decimal("19"))
        LineaVenta.objects.create(venta=venta, producto=self.producto, cantidad=cantidad, precio_unitario=self.producto.precio_venta)
        return venta

    def test_confirmar_venta_descuenta_stock_en_tiempo_real(self):
        venta = self._crear_venta_borrador(cantidad=3)
        venta.confirmar()

        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, 7)
        self.assertEqual(venta.estado, Venta.CONFIRMADA)

        movimiento = MovimientoInventario.objects.latest("id")
        self.assertEqual(movimiento.tipo, MovimientoInventario.SALIDA)
        self.assertEqual(movimiento.motivo, MovimientoInventario.MOTIVO_VENTA)
        self.assertEqual(movimiento.cantidad, 3)
        self.assertEqual(movimiento.stock_resultante, 7)

    def test_no_permite_vender_mas_stock_del_disponible(self):
        venta = self._crear_venta_borrador(cantidad=999)
        with self.assertRaises(ValidationError):
            venta.confirmar()

        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, 10)
        self.assertEqual(venta.estado, Venta.BORRADOR)

    def test_anular_venta_confirmada_devuelve_stock(self):
        venta = self._crear_venta_borrador(cantidad=4)
        venta.confirmar()
        venta.anular()

        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, 10)
        self.assertEqual(venta.estado, Venta.ANULADA)

    def test_calculo_totales_con_impuesto(self):
        venta = self._crear_venta_borrador(cantidad=2)
        self.assertEqual(venta.subtotal, Decimal("20.00"))
        self.assertEqual(venta.impuesto_valor, Decimal("3.80"))
        self.assertEqual(venta.total, Decimal("23.80"))

    def test_no_permite_confirmar_venta_sin_lineas(self):
        venta = Venta.objects.create(cliente=self.cliente)
        with self.assertRaises(ValidationError):
            venta.confirmar()

    def test_confirmar_venta_con_servicio_no_descuenta_stock(self):
        servicio = Producto.objects.create(
            sku="SRV-1", nombre="Instalación", tipo=Producto.SERVICIO,
            categoria=self.categoria, precio_venta=Decimal("50000"),
        )
        venta = Venta.objects.create(cliente=self.cliente, impuesto_porcentaje=Decimal("19"))
        LineaVenta.objects.create(venta=venta, producto=servicio, cantidad=1, precio_unitario=servicio.precio_venta)

        venta.confirmar()

        servicio.refresh_from_db()
        self.assertEqual(servicio.stock_actual, 0)
        self.assertEqual(venta.estado, Venta.CONFIRMADA)
        self.assertFalse(MovimientoInventario.objects.filter(producto=servicio).exists())

    def test_anular_venta_con_servicio_no_genera_movimiento(self):
        servicio = Producto.objects.create(
            sku="SRV-2", nombre="Mantenimiento", tipo=Producto.SERVICIO,
            categoria=self.categoria, precio_venta=Decimal("30000"),
        )
        venta = Venta.objects.create(cliente=self.cliente)
        LineaVenta.objects.create(venta=venta, producto=servicio, cantidad=2, precio_unitario=servicio.precio_venta)
        venta.confirmar()

        venta.anular()

        servicio.refresh_from_db()
        self.assertEqual(servicio.stock_actual, 0)
        self.assertEqual(venta.estado, Venta.ANULADA)
        self.assertFalse(MovimientoInventario.objects.filter(producto=servicio).exists())


class VentaFacturacionTests(TestCase):
    def setUp(self):
        self.categoria = Categoria.objects.create(nombre="General")
        self.producto = Producto.objects.create(
            sku="SKU-1", nombre="Producto de prueba", categoria=self.categoria,
            precio_costo=Decimal("5.00"), precio_venta=Decimal("10.00"),
            stock_actual=10, stock_minimo=2,
        )
        self.cliente = Cliente.objects.create(nombre="Cliente de prueba")

    def _crear_venta_confirmada(self):
        venta = Venta.objects.create(cliente=self.cliente)
        LineaVenta.objects.create(venta=venta, producto=self.producto, cantidad=1, precio_unitario=self.producto.precio_venta)
        venta.confirmar()
        return venta

    def test_no_permite_facturar_venta_no_confirmada(self):
        venta = Venta.objects.create(cliente=self.cliente)
        with self.assertRaises(ValidationError):
            venta.facturar("1001")

    def test_facturar_asigna_numero_y_fecha(self):
        venta = self._crear_venta_confirmada()
        venta.facturar("1001")
        self.assertEqual(venta.numero_factura, "1001")
        self.assertIsNotNone(venta.facturada_en)

    def test_no_permite_facturar_dos_veces(self):
        venta = self._crear_venta_confirmada()
        venta.facturar("1001")
        with self.assertRaises(ValidationError):
            venta.facturar("1002")

    def test_no_permite_numero_factura_repetido(self):
        venta1 = self._crear_venta_confirmada()
        venta1.facturar("1001")

        venta2 = self._crear_venta_confirmada()
        with self.assertRaises(ValidationError):
            venta2.facturar("1001")

    def test_sugerencia_vacia_sin_facturas_previas(self):
        self.assertEqual(Venta.siguiente_numero_factura_sugerido(), "")

    def test_sugerencia_continua_el_consecutivo(self):
        venta1 = self._crear_venta_confirmada()
        venta1.facturar("1001")
        self.assertEqual(Venta.siguiente_numero_factura_sugerido(), "1002")

        venta2 = self._crear_venta_confirmada()
        venta2.facturar(Venta.siguiente_numero_factura_sugerido())
        self.assertEqual(venta2.numero_factura, "1002")
        self.assertEqual(Venta.siguiente_numero_factura_sugerido(), "1003")

    def test_corregir_factura(self):
        venta = self._crear_venta_confirmada()
        venta.facturar("1001")
        venta.corregir_factura("1050")
        self.assertEqual(venta.numero_factura, "1050")

    def test_no_permite_corregir_sin_facturar(self):
        venta = self._crear_venta_confirmada()
        with self.assertRaises(ValidationError):
            venta.corregir_factura("1001")


class VentaFacturacionVistaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="facturador", password="clave-segura-123", email="")
        self.client.force_login(self.user)
        categoria = Categoria.objects.create(nombre="General")
        self.producto = Producto.objects.create(
            sku="SKU-1", nombre="Producto de prueba", categoria=categoria,
            precio_costo=Decimal("5.00"), precio_venta=Decimal("10.00"), stock_actual=10,
        )
        cliente = Cliente.objects.create(nombre="Cliente de prueba")
        self.venta = Venta.objects.create(cliente=cliente)
        LineaVenta.objects.create(venta=self.venta, producto=self.producto, cantidad=1, precio_unitario=self.producto.precio_venta)
        self.venta.confirmar()

    def test_facturar_desde_la_vista(self):
        resp = self.client.post(f"/ventas/ventas/{self.venta.pk}/facturar/", {"numero_factura": "2001"})
        self.assertRedirects(resp, f"/ventas/ventas/{self.venta.pk}/")
        self.venta.refresh_from_db()
        self.assertEqual(self.venta.numero_factura, "2001")

    def test_corregir_desde_la_vista(self):
        self.venta.facturar("2001")
        resp = self.client.post(f"/ventas/ventas/{self.venta.pk}/corregir-factura/", {"numero_factura": "2099"})
        self.assertRedirects(resp, f"/ventas/ventas/{self.venta.pk}/")
        self.venta.refresh_from_db()
        self.assertEqual(self.venta.numero_factura, "2099")

    def test_detalle_muestra_sugerencia(self):
        resp = self.client.get(f"/ventas/ventas/{self.venta.pk}/")
        self.assertContains(resp, "Facturar venta")


class CotizacionTests(TestCase):
    def setUp(self):
        categoria = Categoria.objects.create(nombre="General")
        self.producto = Producto.objects.create(
            sku="SKU-1", nombre="Producto de prueba", categoria=categoria,
            precio_costo=Decimal("5.00"), precio_venta=Decimal("10.00"),
            stock_actual=10, stock_minimo=2,
        )
        self.cliente = Cliente.objects.create(nombre="Cliente de prueba")

    def _crear_cotizacion_borrador(self, cantidad=2):
        cotizacion = Cotizacion.objects.create(cliente=self.cliente, impuesto_porcentaje=Decimal("19"))
        LineaCotizacion.objects.create(
            cotizacion=cotizacion, producto=self.producto, cantidad=cantidad, precio_unitario=self.producto.precio_venta,
        )
        return cotizacion

    def test_numero_se_genera_automaticamente(self):
        cotizacion = self._crear_cotizacion_borrador()
        self.assertTrue(cotizacion.numero.startswith("COT-"))

    def test_fecha_validez_por_defecto_es_15_dias(self):
        cotizacion = self._crear_cotizacion_borrador()
        self.assertEqual(cotizacion.fecha_validez, timezone.localdate() + timezone.timedelta(days=15))

    def test_calculo_totales_con_impuesto(self):
        cotizacion = self._crear_cotizacion_borrador(cantidad=2)
        self.assertEqual(cotizacion.subtotal, Decimal("20.00"))
        self.assertEqual(cotizacion.impuesto_valor, Decimal("3.80"))
        self.assertEqual(cotizacion.total, Decimal("23.80"))

    def test_marcar_enviada_requiere_lineas(self):
        cotizacion = Cotizacion.objects.create(cliente=self.cliente)
        with self.assertRaises(ValidationError):
            cotizacion.marcar_enviada()

    def test_flujo_enviada_aceptada(self):
        cotizacion = self._crear_cotizacion_borrador()
        cotizacion.marcar_enviada()
        self.assertEqual(cotizacion.estado, Cotizacion.ENVIADA)
        self.assertIsNotNone(cotizacion.enviada_en)

        cotizacion.marcar_aceptada(firmado_por="Juan Pérez")
        self.assertEqual(cotizacion.estado, Cotizacion.ACEPTADA)
        self.assertEqual(cotizacion.firmado_por, "Juan Pérez")
        self.assertIsNotNone(cotizacion.firmado_en)

    def test_no_permite_aceptar_sin_enviar(self):
        cotizacion = self._crear_cotizacion_borrador()
        with self.assertRaises(ValidationError):
            cotizacion.marcar_aceptada(firmado_por="Juan Pérez")

    def test_no_permite_aceptar_sin_firma(self):
        cotizacion = self._crear_cotizacion_borrador()
        cotizacion.marcar_enviada()
        with self.assertRaises(ValidationError):
            cotizacion.marcar_aceptada()

    def test_no_permite_editar_tras_enviar(self):
        cotizacion = self._crear_cotizacion_borrador()
        cotizacion.marcar_enviada()
        self.assertFalse(cotizacion.editable)

    def test_convertir_a_venta_copia_lineas_y_no_afecta_stock(self):
        cotizacion = self._crear_cotizacion_borrador(cantidad=3)
        venta = cotizacion.convertir_a_venta()

        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, 10)  # una cotización nunca mueve inventario
        self.assertEqual(venta.estado, Venta.BORRADOR)
        self.assertEqual(venta.lineas.count(), 1)
        self.assertEqual(venta.lineas.first().cantidad, 3)

        cotizacion.refresh_from_db()
        self.assertEqual(cotizacion.venta, venta)

    def test_no_permite_convertir_dos_veces(self):
        cotizacion = self._crear_cotizacion_borrador()
        cotizacion.convertir_a_venta()
        with self.assertRaises(ValidationError):
            cotizacion.convertir_a_venta()

    def test_vencida_solo_si_paso_la_fecha_y_sigue_pendiente(self):
        cotizacion = self._crear_cotizacion_borrador()
        cotizacion.fecha_validez = timezone.localdate() - timezone.timedelta(days=1)
        cotizacion.save(update_fields=["fecha_validez"])
        self.assertTrue(cotizacion.vencida)

        cotizacion.marcar_enviada()
        cotizacion.marcar_aceptada(firmado_por="Juan Pérez")
        self.assertFalse(cotizacion.vencida)  # ya no está pendiente, no importa la fecha


class ClienteCrearRapidoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="vendedor", password="clave-segura-123", email="")
        self.client.force_login(self.user)

    def test_crea_cliente_con_solo_nombre(self):
        resp = self.client.post(
            "/ventas/clientes/nuevo-rapido/",
            {"nombre": "Cliente Exprés", "documento": "", "telefono": "", "email": ""},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        cliente = Cliente.objects.get(pk=data["id"])
        self.assertEqual(cliente.nombre, "Cliente Exprés")
        self.assertTrue(cliente.activo)

    def test_rechaza_sin_nombre(self):
        resp = self.client.post(
            "/ventas/clientes/nuevo-rapido/",
            {"nombre": "", "documento": "", "telefono": "", "email": ""},
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data["ok"])
        self.assertIn("nombre", data["errors"])

    def test_requiere_login(self):
        self.client.logout()
        resp = self.client.post("/ventas/clientes/nuevo-rapido/", {"nombre": "Sin sesión"})
        self.assertNotEqual(resp.status_code, 200)

    def test_requiere_post(self):
        resp = self.client.get("/ventas/clientes/nuevo-rapido/")
        self.assertEqual(resp.status_code, 405)
