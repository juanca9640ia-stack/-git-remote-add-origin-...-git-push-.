from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from inventario.models import Producto
from ventas.models import Cliente, Cotizacion, CuentaCobro

from .models import ItemBitacora, Sede


class SedeModeloTests(TestCase):
    def test_no_permite_dos_sedes_con_el_mismo_nombre_para_el_mismo_cliente(self):
        cliente = Cliente.objects.create(nombre="Cliente de prueba")
        Sede.objects.create(cliente=cliente, nombre="Violetas")
        with self.assertRaises(Exception):
            Sede.objects.create(cliente=cliente, nombre="Violetas")


class ItemBitacoraModeloTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(nombre="Cliente de prueba")
        self.sede = Sede.objects.create(cliente=self.cliente, nombre="San Rafael")

    def test_subtotal_es_cantidad_por_valor_unitario(self):
        item = ItemBitacora.objects.create(
            sede=self.sede, descripcion="Cambio de bombillo", cantidad=Decimal("3"),
            valor_unitario=Decimal("15000"),
        )
        self.assertEqual(item.subtotal, Decimal("45000"))

    def test_no_esta_facturado_por_defecto(self):
        item = ItemBitacora.objects.create(sede=self.sede, descripcion="Poda de jardín")
        self.assertFalse(item.facturado)

    def test_queda_facturado_al_asociar_cuenta_de_cobro(self):
        cuenta = CuentaCobro.objects.create(cliente=self.cliente, concepto="Trabajo varios", valor=Decimal("1"))
        item = ItemBitacora.objects.create(sede=self.sede, descripcion="Poda de jardín", cuenta_cobro=cuenta)
        self.assertTrue(item.facturado)


class BitacoraVistasTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="gerente", password="clave-segura-123", email="")
        self.client.force_login(self.user)
        self.cliente = Cliente.objects.create(nombre="Cliente de prueba")
        self.sede = Sede.objects.create(cliente=self.cliente, nombre="Bombona")

    def test_sede_lista_muestra_las_sedes_de_la_empresa(self):
        resp = self.client.get("/bitacora/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Bombona")

    def test_crear_sede_desde_el_formulario(self):
        resp = self.client.post("/bitacora/nueva/", {
            "cliente": self.cliente.pk, "nombre": "San Rafael", "direccion": "Cra 1 # 2-3", "activa": "on",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Sede.objects.filter(nombre="San Rafael", cliente=self.cliente).exists())

    def test_sede_lista_incluye_el_formulario_rapido_de_alta(self):
        resp = self.client.get("/bitacora/")
        self.assertContains(resp, "Agregar sede")
        self.assertContains(resp, 'action="/bitacora/nueva/"')

    def test_alta_rapida_de_sede_desde_la_lista_se_queda_en_la_misma_hoja(self):
        resp = self.client.post("/bitacora/nueva/", {
            "cliente": self.cliente.pk, "nombre": "Violetas", "direccion": "",
            "activa": "on", "origen": "lista",
        })
        self.assertRedirects(resp, "/bitacora/")
        nueva = Sede.objects.get(nombre="Violetas", cliente=self.cliente)
        self.assertTrue(nueva.activa)

    def test_alta_rapida_permite_agregar_varias_sedes_seguidas(self):
        for nombre in ["San Rafael", "Bombona 2", "Portal Norte"]:
            resp = self.client.post("/bitacora/nueva/", {
                "cliente": self.cliente.pk, "nombre": nombre, "direccion": "",
                "activa": "on", "origen": "lista",
            })
            self.assertRedirects(resp, "/bitacora/")
        self.assertEqual(Sede.objects.filter(cliente=self.cliente).count(), 4)  # + Bombona del setUp

    def test_sede_detalle_muestra_todas_las_sedes_del_cliente_apiladas_en_una_hoja(self):
        otra = Sede.objects.create(cliente=self.cliente, nombre="Violetas")
        ItemBitacora.objects.create(sede=self.sede, descripcion="Trabajo en Bombona")
        ItemBitacora.objects.create(sede=otra, descripcion="Trabajo en Violetas")

        resp = self.client.get(f"/bitacora/{self.sede.pk}/")
        sedes_en_bloques = [b["sede"] for b in resp.context["bloques"]]
        self.assertIn(self.sede, sedes_en_bloques)
        self.assertIn(otra, sedes_en_bloques)
        self.assertContains(resp, "Bombona")
        self.assertContains(resp, "Violetas")
        self.assertContains(resp, "Trabajo en Bombona")
        self.assertContains(resp, "Trabajo en Violetas")
        self.assertContains(resp, 'id="sede-')

    def test_cada_bloque_de_sede_tiene_su_propio_formulario_de_alta_de_items(self):
        otra = Sede.objects.create(cliente=self.cliente, nombre="Violetas")
        resp = self.client.get(f"/bitacora/{self.sede.pk}/")
        self.assertContains(resp, f'action="/bitacora/{self.sede.pk}/items/nuevo/"')
        self.assertContains(resp, f'action="/bitacora/{otra.pk}/items/nuevo/"')

    def test_agregar_sede_desde_la_hoja_de_otra_sede_se_queda_en_la_hoja_de_origen(self):
        resp = self.client.post("/bitacora/nueva/", {
            "cliente": self.cliente.pk, "nombre": "San Rafael", "direccion": "",
            "activa": "on", "origen": "sede", "volver": self.sede.pk,
        })
        self.assertRedirects(resp, f"/bitacora/{self.sede.pk}/")
        self.assertTrue(Sede.objects.filter(nombre="San Rafael", cliente=self.cliente).exists())

    def test_agregar_item_a_la_bitacora_de_una_sede(self):
        resp = self.client.post(f"/bitacora/{self.sede.pk}/items/nuevo/", {
            "fecha": timezone.localdate().isoformat(), "descripcion": "Cambio de tomacorriente",
            "unidad": "un", "cantidad": "2", "valor_unitario": "20000", "notas": "",
        })
        self.assertEqual(resp.status_code, 302)
        item = ItemBitacora.objects.get(sede=self.sede)
        self.assertEqual(item.subtotal, Decimal("40000"))

    def test_no_permite_eliminar_un_item_ya_facturado(self):
        cuenta = CuentaCobro.objects.create(cliente=self.cliente, concepto="x", valor=Decimal("1"))
        item = ItemBitacora.objects.create(sede=self.sede, descripcion="Trabajo x", cuenta_cobro=cuenta)
        resp = self.client.post(f"/bitacora/{self.sede.pk}/items/{item.pk}/eliminar/")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(ItemBitacora.objects.filter(pk=item.pk).exists())

    def test_exportar_excel_descarga_un_archivo_xlsx(self):
        ItemBitacora.objects.create(sede=self.sede, descripcion="Trabajo x", cantidad=1, valor_unitario=Decimal("1000"))
        resp = self.client.get(f"/bitacora/{self.sede.pk}/exportar/excel/?todo=1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_exportar_pdf_renderiza_la_pagina_imprimible(self):
        ItemBitacora.objects.create(sede=self.sede, descripcion="Trabajo x", cantidad=1, valor_unitario=Decimal("1000"))
        resp = self.client.get(f"/bitacora/{self.sede.pk}/exportar/pdf/?todo=1")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Trabajo x")
        self.assertContains(resp, "Imprimir / Guardar como PDF")


class GenerarDocumentoDesdeBitacoraTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="gerente", password="clave-segura-123", email="")
        self.client.force_login(self.user)
        self.cliente = Cliente.objects.create(nombre="Cliente de prueba")
        self.sede = Sede.objects.create(cliente=self.cliente, nombre="Violetas")
        self.item1 = ItemBitacora.objects.create(
            sede=self.sede, descripcion="Cambio de bombillo", cantidad=Decimal("2"),
            valor_unitario=Decimal("15000"),
        )
        self.item2 = ItemBitacora.objects.create(
            sede=self.sede, descripcion="Poda de jardín", cantidad=Decimal("1"),
            valor_unitario=Decimal("50000"),
        )

    def test_generar_cuenta_de_cobro_agrupa_los_items_pendientes(self):
        resp = self.client.post(f"/bitacora/{self.sede.pk}/generar/cuenta-cobro/")
        self.assertEqual(resp.status_code, 302)
        cuenta = CuentaCobro.objects.get(cliente=self.cliente)
        self.assertEqual(cuenta.valor, Decimal("80000"))
        self.assertIn("Cambio de bombillo", cuenta.concepto)
        self.assertIn("Poda de jardín", cuenta.concepto)

        self.item1.refresh_from_db()
        self.item2.refresh_from_db()
        self.assertEqual(self.item1.cuenta_cobro, cuenta)
        self.assertTrue(self.item1.facturado)

    def test_generar_cuenta_de_cobro_sin_pendientes_no_crea_nada(self):
        self.item1.delete()
        self.item2.delete()
        resp = self.client.post(f"/bitacora/{self.sede.pk}/generar/cuenta-cobro/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(CuentaCobro.objects.count(), 0)

    def test_generar_cotizacion_crea_productos_de_servicio_y_lineas(self):
        resp = self.client.post(f"/bitacora/{self.sede.pk}/generar/cotizacion/")
        self.assertEqual(resp.status_code, 302)

        cotizacion = Cotizacion.objects.get(cliente=self.cliente)
        self.assertEqual(cotizacion.lineas.count(), 2)
        self.assertEqual(cotizacion.subtotal, Decimal("80000"))

        producto = Producto.objects.get(nombre__iexact="Cambio de bombillo")
        self.assertEqual(producto.tipo, Producto.SERVICIO)

        self.item1.refresh_from_db()
        self.assertEqual(self.item1.cotizacion, cotizacion)

    def test_generar_cotizacion_reutiliza_producto_existente_por_descripcion(self):
        self.client.post(f"/bitacora/{self.sede.pk}/generar/cotizacion/")
        total_productos = Producto.objects.filter(tipo=Producto.SERVICIO).count()

        otra_sede = Sede.objects.create(cliente=self.cliente, nombre="San Rafael")
        ItemBitacora.objects.create(sede=otra_sede, descripcion="Cambio de bombillo", cantidad=1, valor_unitario=Decimal("15000"))
        self.client.post(f"/bitacora/{otra_sede.pk}/generar/cotizacion/")

        self.assertEqual(Producto.objects.filter(tipo=Producto.SERVICIO).count(), total_productos)

    def test_items_ya_facturados_no_se_incluyen_de_nuevo(self):
        self.client.post(f"/bitacora/{self.sede.pk}/generar/cuenta-cobro/")
        resp = self.client.post(f"/bitacora/{self.sede.pk}/generar/cotizacion/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Cotizacion.objects.count(), 0)
