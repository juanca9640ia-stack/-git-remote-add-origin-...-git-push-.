from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from inventario.models import Categoria, MovimientoInventario, Producto
from produccion.models import ComponenteBOM, ListaMateriales, OrdenProduccion


class OrdenProduccionIntegrationTests(TestCase):
    def setUp(self):
        categoria = Categoria.objects.create(nombre="General")
        self.tela = Producto.objects.create(
            sku="INS-1", nombre="Tela", categoria=categoria,
            precio_costo=Decimal("3.00"), precio_venta=0, stock_actual=100, stock_minimo=10,
        )
        self.hilo = Producto.objects.create(
            sku="INS-2", nombre="Hilo", categoria=categoria,
            precio_costo=Decimal("0.50"), precio_venta=0, stock_actual=50, stock_minimo=5,
        )
        self.camiseta = Producto.objects.create(
            sku="PT-1", nombre="Camiseta", categoria=categoria,
            precio_costo=Decimal("8.00"), precio_venta=Decimal("20.00"), stock_actual=0, stock_minimo=5,
        )
        self.lista = ListaMateriales.objects.create(producto=self.camiseta)
        ComponenteBOM.objects.create(lista=self.lista, insumo=self.tela, cantidad_por_unidad=2)
        ComponenteBOM.objects.create(lista=self.lista, insumo=self.hilo, cantidad_por_unidad=1)

    def _crear_orden(self, cantidad=5):
        orden = OrdenProduccion.objects.create(producto=self.camiseta, cantidad=cantidad)
        orden.sincronizar_componentes_desde_receta()
        return orden

    def test_completar_orden_consume_insumos_y_genera_producto_terminado(self):
        orden = self._crear_orden(cantidad=5)
        orden.completar()

        self.tela.refresh_from_db()
        self.hilo.refresh_from_db()
        self.camiseta.refresh_from_db()

        self.assertEqual(self.tela.stock_actual, 90)   # 100 - (2 x 5)
        self.assertEqual(self.hilo.stock_actual, 45)    # 50 - (1 x 5)
        self.assertEqual(self.camiseta.stock_actual, 5)  # 0 + 5
        self.assertEqual(orden.estado, OrdenProduccion.COMPLETADA)

        movimientos_produccion = MovimientoInventario.objects.filter(motivo=MovimientoInventario.MOTIVO_PRODUCCION)
        self.assertEqual(movimientos_produccion.count(), 3)  # 2 salidas de insumos + 1 entrada de terminado

    def test_no_permite_completar_sin_componentes(self):
        orden = OrdenProduccion.objects.create(producto=self.camiseta, cantidad=1)
        with self.assertRaises(ValidationError):
            orden.completar()

    def test_no_permite_completar_si_insumo_insuficiente(self):
        orden = self._crear_orden(cantidad=1000)  # requiere 2000 de tela, solo hay 100
        with self.assertRaises(ValidationError):
            orden.completar()
        orden.refresh_from_db()
        self.assertEqual(orden.estado, OrdenProduccion.PLANIFICADA)

    def test_anular_orden_completada_revierte_stock(self):
        orden = self._crear_orden(cantidad=5)
        orden.completar()
        orden.anular()

        self.tela.refresh_from_db()
        self.hilo.refresh_from_db()
        self.camiseta.refresh_from_db()

        self.assertEqual(self.tela.stock_actual, 100)
        self.assertEqual(self.hilo.stock_actual, 50)
        self.assertEqual(self.camiseta.stock_actual, 0)
        self.assertEqual(orden.estado, OrdenProduccion.ANULADA)

    def test_no_permite_anular_si_ya_no_hay_stock_del_terminado(self):
        orden = self._crear_orden(cantidad=5)
        orden.completar()

        self.camiseta.refresh_from_db()
        self.camiseta.stock_actual = 0  # se vendieron las camisetas producidas
        self.camiseta.save(update_fields=["stock_actual"])

        with self.assertRaises(ValidationError):
            orden.anular()

    def test_sincronizar_componentes_recalcula_cantidades(self):
        orden = self._crear_orden(cantidad=5)
        self.assertEqual(orden.componentes.get(insumo=self.tela).cantidad_requerida, 10)

        orden.cantidad = 10
        orden.save()
        orden.sincronizar_componentes_desde_receta()
        self.assertEqual(orden.componentes.get(insumo=self.tela).cantidad_requerida, 20)
        self.assertEqual(orden.componentes.count(), 2)
