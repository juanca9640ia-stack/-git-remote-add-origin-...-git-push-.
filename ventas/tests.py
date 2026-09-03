from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from inventario.models import Categoria, MovimientoInventario, Producto
from ventas.models import Cliente, Cotizacion, CuentaCobro, LineaCotizacion, LineaVenta, Venta


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
        self.assertEqual(Venta.siguiente_numero_factura_sugerido(self.cliente.empresa), "")

    def test_sugerencia_continua_el_consecutivo(self):
        venta1 = self._crear_venta_confirmada()
        venta1.facturar("1001")
        self.assertEqual(Venta.siguiente_numero_factura_sugerido(self.cliente.empresa), "1002")

        venta2 = self._crear_venta_confirmada()
        venta2.facturar(Venta.siguiente_numero_factura_sugerido(self.cliente.empresa))
        self.assertEqual(venta2.numero_factura, "1002")
        self.assertEqual(Venta.siguiente_numero_factura_sugerido(self.cliente.empresa), "1003")

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

    def test_convertir_a_venta_fija_iva_en_19_sin_importar_el_de_la_cotizacion(self):
        cotizacion = Cotizacion.objects.create(cliente=self.cliente, impuesto_porcentaje=Decimal("5"))
        LineaCotizacion.objects.create(
            cotizacion=cotizacion, producto=self.producto, cantidad=1, precio_unitario=self.producto.precio_venta,
        )
        venta = cotizacion.convertir_a_venta()
        self.assertEqual(venta.impuesto_porcentaje, Decimal("19"))

    def test_convertir_a_proyecto_crea_obra_con_el_cliente_y_el_total_cotizado(self):
        cotizacion = self._crear_cotizacion_borrador(cantidad=2)
        proyecto = cotizacion.convertir_a_proyecto()

        self.assertEqual(proyecto.cliente, self.cliente)
        self.assertEqual(proyecto.presupuesto, cotizacion.total)
        cotizacion.refresh_from_db()
        self.assertEqual(cotizacion.proyecto, proyecto)

    def test_no_permite_convertir_a_proyecto_dos_veces(self):
        cotizacion = self._crear_cotizacion_borrador()
        cotizacion.convertir_a_proyecto()
        with self.assertRaises(ValidationError):
            cotizacion.convertir_a_proyecto()

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


class CuentaCobroModelTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(nombre="Cliente de prueba", documento="123456")

    def test_numero_consecutivo_se_asigna_al_guardar(self):
        cuenta = CuentaCobro.objects.create(
            cliente=self.cliente, concepto="Servicio de prueba", valor=Decimal("100000"),
        )
        self.assertEqual(cuenta.numero, f"CC-{cuenta.pk:06d}")

    def test_persona_natural_requiere_nombre_y_documento(self):
        cuenta = CuentaCobro(
            cliente=self.cliente, concepto="Servicio", valor=Decimal("50000"),
            emisor_tipo=CuentaCobro.PERSONA_NATURAL,
        )
        with self.assertRaises(ValidationError):
            cuenta.full_clean()

    def test_flujo_borrador_emitida_pagada(self):
        cuenta = CuentaCobro.objects.create(
            cliente=self.cliente, concepto="Servicio", valor=Decimal("50000"),
        )
        self.assertTrue(cuenta.editable)

        cuenta.emitir()
        self.assertEqual(cuenta.estado, CuentaCobro.EMITIDA)
        self.assertIsNotNone(cuenta.emitida_en)
        self.assertFalse(cuenta.editable)

        cuenta.marcar_pagada()
        self.assertEqual(cuenta.estado, CuentaCobro.PAGADA)

    def test_no_se_puede_emitir_dos_veces(self):
        cuenta = CuentaCobro.objects.create(
            cliente=self.cliente, concepto="Servicio", valor=Decimal("50000"),
        )
        cuenta.emitir()
        with self.assertRaises(ValidationError):
            cuenta.emitir()

    def test_anular_borrador_y_emitida(self):
        cuenta = CuentaCobro.objects.create(
            cliente=self.cliente, concepto="Servicio", valor=Decimal("50000"),
        )
        cuenta.anular()
        self.assertEqual(cuenta.estado, CuentaCobro.ANULADA)

        otra = CuentaCobro.objects.create(
            cliente=self.cliente, concepto="Servicio", valor=Decimal("50000"),
        )
        otra.emitir()
        otra.anular()
        self.assertEqual(otra.estado, CuentaCobro.ANULADA)

    def test_no_se_puede_anular_pagada(self):
        cuenta = CuentaCobro.objects.create(
            cliente=self.cliente, concepto="Servicio", valor=Decimal("50000"),
        )
        cuenta.emitir()
        cuenta.marcar_pagada()
        with self.assertRaises(ValidationError):
            cuenta.anular()


class CuentaCobroVistaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="cobrador", password="clave-segura-123", email="")
        self.client.force_login(self.user)
        self.cliente = Cliente.objects.create(nombre="Cliente natural", documento="999")

    def test_crear_cuenta_de_cobro_a_nombre_de_la_empresa(self):
        resp = self.client.post("/ventas/cuentas-cobro/nueva/", {
            "cliente": self.cliente.pk, "emisor_tipo": "empresa",
            "concepto": "Diseño de logo", "valor": "300000", "fecha": "2026-09-01",
            "forma_pago": "", "datos_pago": "",
        })
        cuenta = CuentaCobro.objects.get(cliente=self.cliente)
        self.assertRedirects(resp, f"/ventas/cuentas-cobro/{cuenta.pk}/")
        self.assertEqual(cuenta.emisor_tipo, "empresa")

    def test_crear_cuenta_de_cobro_a_nombre_de_persona_natural(self):
        resp = self.client.post("/ventas/cuentas-cobro/nueva/", {
            "cliente": self.cliente.pk, "emisor_tipo": "persona_natural",
            "emisor_nombre": "Juan Pérez", "emisor_documento": "1002003004",
            "concepto": "Mano de obra", "valor": "150000", "fecha": "2026-09-01",
            "forma_pago": "", "datos_pago": "",
        })
        cuenta = CuentaCobro.objects.get(cliente=self.cliente)
        self.assertRedirects(resp, f"/ventas/cuentas-cobro/{cuenta.pk}/")
        self.assertEqual(cuenta.emisor_nombre, "Juan Pérez")

    def test_rechaza_persona_natural_sin_documento(self):
        resp = self.client.post("/ventas/cuentas-cobro/nueva/", {
            "cliente": self.cliente.pk, "emisor_tipo": "persona_natural",
            "emisor_nombre": "Juan Pérez", "emisor_documento": "",
            "concepto": "Mano de obra", "valor": "150000", "fecha": "2026-09-01",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(CuentaCobro.objects.filter(cliente=self.cliente).exists())

    def test_no_se_puede_editar_una_cuenta_emitida(self):
        cuenta = CuentaCobro.objects.create(
            cliente=self.cliente, concepto="Servicio", valor=Decimal("50000"),
        )
        cuenta.emitir()
        resp = self.client.get(f"/ventas/cuentas-cobro/{cuenta.pk}/editar/")
        self.assertRedirects(resp, f"/ventas/cuentas-cobro/{cuenta.pk}/")

    def test_imprimir_muestra_valor_en_letras(self):
        cuenta = CuentaCobro.objects.create(
            cliente=self.cliente, concepto="Servicio de pintura", valor=Decimal("150000"),
        )
        cuenta.emitir()
        resp = self.client.get(f"/ventas/cuentas-cobro/{cuenta.pk}/imprimir/")
        self.assertContains(resp, "CIENTO CINCUENTA MIL PESOS M/CTE")


class FlujoIntegracionDocumentosTests(TestCase):
    """Fase de integración: elegir tipo de documento, y cotización -> proyecto /
    factura / cuenta de cobro sin volver a pedir la información."""

    def setUp(self):
        self.user = User.objects.create_superuser(username="gerente", password="clave-segura-123", email="")
        self.client.force_login(self.user)
        categoria = Categoria.objects.create(nombre="General")
        self.producto = Producto.objects.create(
            sku="SKU-1", nombre="Producto de prueba", categoria=categoria,
            precio_costo=Decimal("5.00"), precio_venta=Decimal("100000.00"), stock_actual=10,
        )
        self.cliente = Cliente.objects.create(nombre="Cliente de prueba")
        self.cotizacion = Cotizacion.objects.create(cliente=self.cliente, impuesto_porcentaje=Decimal("19"))
        LineaCotizacion.objects.create(
            cotizacion=self.cotizacion, producto=self.producto, cantidad=2, precio_unitario=Decimal("100000.00"),
        )
        self.cotizacion.marcar_enviada()
        self.cotizacion.marcar_aceptada(firmado_por="Cliente de prueba")

    def test_elegir_documento_ofrece_las_dos_rutas(self):
        resp = self.client.get(f"/ventas/nuevo-documento/?cliente={self.cliente.pk}")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Factura")
        self.assertContains(resp, "Cuenta de cobro")
        self.assertContains(resp, f"/ventas/ventas/nueva/?cliente={self.cliente.pk}")
        self.assertContains(resp, f"/ventas/cuentas-cobro/nueva/?cliente={self.cliente.pk}")

    def test_venta_form_no_permite_editar_el_iva(self):
        resp = self.client.get("/ventas/ventas/nueva/")
        self.assertNotContains(resp, 'name="impuesto_porcentaje"')

    def test_venta_creada_desde_formulario_queda_en_19_por_ciento(self):
        resp = self.client.post("/ventas/ventas/nueva/", {
            "cliente": self.cliente.pk,
            "lineas-TOTAL_FORMS": "1", "lineas-INITIAL_FORMS": "0",
            "lineas-MIN_NUM_FORMS": "0", "lineas-MAX_NUM_FORMS": "1000",
            "lineas-0-producto": self.producto.pk, "lineas-0-cantidad": "1",
            "lineas-0-precio_unitario": "100000.00",
        })
        venta = Venta.objects.get(cliente=self.cliente)
        self.assertRedirects(resp, f"/ventas/ventas/{venta.pk}/")
        self.assertEqual(venta.impuesto_porcentaje, Decimal("19"))

    def test_convertir_cotizacion_en_proyecto_desde_la_vista(self):
        resp = self.client.post(f"/ventas/cotizaciones/{self.cotizacion.pk}/convertir-proyecto/")
        self.cotizacion.refresh_from_db()
        self.assertRedirects(resp, f"/proyectos/{self.cotizacion.proyecto.pk}/")
        self.assertEqual(self.cotizacion.proyecto.cliente, self.cliente)

    def test_generar_cuenta_de_cobro_desde_cotizacion_prellena_los_datos(self):
        resp = self.client.get(f"/ventas/cuentas-cobro/nueva/?cotizacion={self.cotizacion.pk}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["form"].initial["cliente"], self.cliente.pk)
        self.assertEqual(resp.context["form"].initial["valor"], self.cotizacion.total)

    def test_cuenta_de_cobro_generada_desde_cotizacion_queda_vinculada(self):
        resp = self.client.post(f"/ventas/cuentas-cobro/nueva/?cotizacion={self.cotizacion.pk}", {
            "cliente": self.cliente.pk, "emisor_tipo": "empresa",
            "concepto": f"Según cotización {self.cotizacion.numero}.", "valor": str(self.cotizacion.total),
            "fecha": "2026-09-01",
        })
        cuenta = CuentaCobro.objects.get(cliente=self.cliente)
        self.assertRedirects(resp, f"/ventas/cuentas-cobro/{cuenta.pk}/")
        self.assertEqual(cuenta.cotizacion_id, self.cotizacion.pk)

    def test_generar_factura_desde_proyecto_prellena_lineas_de_la_cotizacion(self):
        proyecto = self.cotizacion.convertir_a_proyecto()
        resp = self.client.get(f"/ventas/ventas/nueva/?proyecto={proyecto.pk}&cliente={self.cliente.pk}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(int(resp.context["form"].initial["cliente"]), self.cliente.pk)
        # Las líneas prellenadas viven en initial_extra (así es como Django
        # alimenta los formularios "extra" de un ModelFormSet sin instancia).
        lineas = resp.context["formset"].initial_extra
        self.assertEqual(len(lineas), 1)
        self.assertEqual(lineas[0]["producto"], self.producto.pk)
        self.assertEqual(lineas[0]["cantidad"], 2)
        # Y también deben quedar reflejadas en el primer formulario ya renderizado.
        self.assertEqual(resp.context["formset"].forms[0].initial["producto"], self.producto.pk)

    def test_generar_cuenta_de_cobro_desde_proyecto_incluye_descripcion_del_producto(self):
        self.producto.descripcion = "Cemento gris tipo I, bulto de 50kg"
        self.producto.save(update_fields=["descripcion"])
        proyecto = self.cotizacion.convertir_a_proyecto()

        resp = self.client.get(f"/ventas/cuentas-cobro/nueva/?proyecto={proyecto.pk}&cliente={self.cliente.pk}")
        self.assertEqual(resp.status_code, 200)
        concepto = resp.context["form"].initial["concepto"]
        self.assertIn(self.producto.nombre, concepto)
        self.assertIn("Cemento gris tipo I, bulto de 50kg", concepto)
        self.assertIn(self.cotizacion.numero, concepto)


class VentaImprimirTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="viewer", password="clave-segura-123", email="")
        self.client.force_login(self.user)
        categoria = Categoria.objects.create(nombre="General")
        self.producto = Producto.objects.create(
            sku="SKU-1", nombre="Producto de prueba", categoria=categoria,
            precio_costo=Decimal("5.00"), precio_venta=Decimal("100000.00"), stock_actual=10,
        )
        self.cliente = Cliente.objects.create(nombre="Cliente de prueba")
        self.venta = Venta.objects.create(cliente=self.cliente)
        LineaVenta.objects.create(venta=self.venta, producto=self.producto, cantidad=1, precio_unitario=Decimal("100000.00"))
        self.venta.confirmar()
        self.venta.facturar("3001")

    def test_muestra_numero_de_factura_y_totales(self):
        resp = self.client.get(f"/ventas/ventas/{self.venta.pk}/imprimir/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "FACTURA DE VENTA")
        self.assertContains(resp, "3001")
        self.assertContains(resp, "IVA (19")


class ClienteDetalle360Tests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="gerente360", password="clave-segura-123", email="")
        self.client.force_login(self.user)
        self.cliente = Cliente.objects.create(nombre="Cliente 360")

    def test_muestra_proyectos_del_cliente(self):
        from proyectos.models import Proyecto

        proyecto = Proyecto.objects.create(nombre="Obra del cliente", cliente=self.cliente)
        resp = self.client.get(f"/ventas/clientes/{self.cliente.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(proyecto, list(resp.context["proyectos"]))

    def test_muestra_pagos_recibidos(self):
        from finanzas.models import CuentaPorCobrar, PagoCliente

        categoria = Categoria.objects.create(nombre="General")
        producto = Producto.objects.create(
            sku="SKU-1", nombre="Producto", categoria=categoria,
            precio_costo=Decimal("5"), precio_venta=Decimal("100000"), stock_actual=10,
        )
        venta = Venta.objects.create(cliente=self.cliente)
        LineaVenta.objects.create(venta=venta, producto=producto, cantidad=1, precio_unitario=Decimal("100000"))
        venta.confirmar()
        cuenta = CuentaPorCobrar.objects.get(venta=venta)
        cuenta.registrar_pago(monto=Decimal("50000"), metodo="efectivo", referencia="", usuario=self.user)

        resp = self.client.get(f"/ventas/clientes/{self.cliente.pk}/")
        pagos = list(resp.context["pagos"])
        self.assertEqual(len(pagos), 1)
        self.assertEqual(pagos[0].monto, Decimal("50000"))

    def test_muestra_las_sedes_del_cliente(self):
        from bitacora.models import Sede

        sede = Sede.objects.create(cliente=self.cliente, nombre="Violetas")
        resp = self.client.get(f"/ventas/clientes/{self.cliente.pk}/")
        self.assertIn(sede, list(resp.context["sedes"]))
        self.assertContains(resp, "Violetas")

    def test_agregar_sede_desde_la_ficha_del_cliente_se_queda_en_la_misma_hoja(self):
        from bitacora.models import Sede

        resp = self.client.post("/bitacora/nueva/", {
            "cliente": self.cliente.pk, "nombre": "San Rafael", "direccion": "",
            "activa": "on", "origen": "cliente",
        })
        self.assertRedirects(resp, f"/ventas/clientes/{self.cliente.pk}/")
        self.assertTrue(Sede.objects.filter(nombre="San Rafael", cliente=self.cliente).exists())
