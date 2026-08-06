from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from inventario.models import Categoria, Producto


class ProductoTipoTests(TestCase):
    def setUp(self):
        self.categoria = Categoria.objects.create(nombre="General")

    def test_producto_por_defecto_es_tipo_producto(self):
        producto = Producto.objects.create(
            sku="SKU-1", nombre="Camiseta", categoria=self.categoria,
            precio_venta=Decimal("20.00"), stock_actual=5, stock_minimo=10,
        )
        self.assertEqual(producto.tipo, Producto.PRODUCTO)
        self.assertFalse(producto.es_servicio)
        self.assertTrue(producto.stock_bajo)

    def test_servicio_nunca_tiene_stock_bajo(self):
        servicio = Producto.objects.create(
            sku="SRV-1", nombre="Instalación", tipo=Producto.SERVICIO,
            precio_venta=Decimal("50000"), stock_actual=0, stock_minimo=0,
        )
        self.assertTrue(servicio.es_servicio)
        self.assertFalse(servicio.stock_bajo)


class ProductoCrearRapidoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="operador", password="clave-segura-123", email="")
        self.client.force_login(self.user)

    def test_crea_producto_con_sku_automatico(self):
        resp = self.client.post(
            "/inventario/productos/nuevo-rapido/",
            {"nombre": "Cuaderno", "sku": "", "descripcion": "", "tipo": "producto",
             "precio_venta": "5000", "stock_actual": "10", "stock_minimo": "2"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        producto = Producto.objects.get(pk=data["id"])
        self.assertTrue(producto.sku.startswith("AUTO-"))
        self.assertEqual(producto.stock_actual, 10)

    def test_crea_servicio_ignora_stock_enviado(self):
        resp = self.client.post(
            "/inventario/productos/nuevo-rapido/",
            {"nombre": "Consultoría", "sku": "", "descripcion": "Asesoría por hora", "tipo": "servicio",
             "precio_venta": "80000", "stock_actual": "999", "stock_minimo": "5"},
        )
        data = resp.json()
        self.assertTrue(data["ok"])
        producto = Producto.objects.get(pk=data["id"])
        self.assertTrue(producto.es_servicio)
        self.assertEqual(producto.stock_actual, 0)
        self.assertEqual(producto.stock_minimo, 0)
        self.assertEqual(data["descripcion"], "Asesoría por hora")

    def test_rechaza_sin_nombre(self):
        resp = self.client.post(
            "/inventario/productos/nuevo-rapido/",
            {"nombre": "", "sku": "", "descripcion": "", "tipo": "producto", "precio_venta": "0"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["ok"])


class ServicioListaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="operador2", password="clave-segura-123", email="")
        self.client.force_login(self.user)
        self.categoria = Categoria.objects.create(nombre="General")
        self.producto = Producto.objects.create(
            sku="SKU-1", nombre="Camiseta", categoria=self.categoria, precio_venta=Decimal("20.00"),
        )
        self.servicio = Producto.objects.create(
            sku="SRV-1", nombre="Instalación", tipo=Producto.SERVICIO, precio_venta=Decimal("50000"),
        )

    def test_solo_lista_servicios(self):
        resp = self.client.get("/inventario/servicios/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Instalación")
        self.assertNotContains(resp, "Camiseta")
