from django.core.management.base import BaseCommand
from django.db import connection, transaction

from compras.models import Compra, LineaCompra, Proveedor
from finanzas.models import CuentaPorCobrar, CuentaPorPagar, PagoCliente, PagoProveedor
from inventario.models import Categoria, MovimientoInventario, Producto
from produccion.models import ComponenteBOM, ComponenteOrdenProduccion, ListaMateriales, OrdenProduccion
from rrhh.models import AbonoPrestamo, Asistencia, Departamento, DetalleNomina, Empleado, Nomina, Prestamo
from ventas.models import Cliente, Cotizacion, LineaCotizacion, LineaVenta, Venta

MODELOS_A_BORRAR = [
    PagoCliente, PagoProveedor, CuentaPorCobrar, CuentaPorPagar,
    AbonoPrestamo, Prestamo, DetalleNomina, Nomina, Asistencia, Empleado, Departamento,
    ComponenteOrdenProduccion, OrdenProduccion, ComponenteBOM, ListaMateriales,
    LineaCotizacion, Cotizacion, LineaVenta, Venta, Cliente,
    LineaCompra, Compra, Proveedor,
    MovimientoInventario, Producto, Categoria,
]


class Command(BaseCommand):
    help = (
        "Borra todos los datos de negocio (ventas, compras, inventario, producción, nómina, "
        "préstamos, etc.) para dejar el sistema listo para pruebas reales. Conserva usuarios, "
        "grupos de permisos y la configuración de la empresa."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes", action="store_true",
            help="Ejecuta sin pedir confirmación interactiva.",
        )

    def handle(self, *args, **options):
        if not options["yes"]:
            respuesta = input(
                "Esto borrará TODOS los datos de negocio (ventas, compras, cotizaciones, inventario, "
                "producción, nómina, préstamos, empleados, clientes, proveedores). Los usuarios, grupos "
                "de permisos y la configuración de la empresa se conservan. Escribe 'si' para continuar: "
            )
            if respuesta.strip().lower() not in ("si", "sí", "yes"):
                self.stdout.write(self.style.WARNING("Cancelado, no se borró nada."))
                return

        with transaction.atomic():
            # Finanzas primero: protegen venta/compra/nómina hasta que se borren sus pagos y cuentas.
            PagoCliente.objects.all().delete()
            PagoProveedor.objects.all().delete()
            CuentaPorCobrar.objects.all().delete()
            CuentaPorPagar.objects.all().delete()

            # RR.HH.
            AbonoPrestamo.objects.all().delete()
            Prestamo.objects.all().delete()
            DetalleNomina.objects.all().delete()
            Nomina.objects.all().delete()
            Asistencia.objects.all().delete()
            Empleado.objects.all().delete()
            Departamento.objects.all().delete()

            # Producción (antes de tocar productos, por las referencias PROTECT a insumos).
            ComponenteOrdenProduccion.objects.all().delete()
            OrdenProduccion.objects.all().delete()
            ComponenteBOM.objects.all().delete()
            ListaMateriales.objects.all().delete()

            # Ventas y cotizaciones
            LineaCotizacion.objects.all().delete()
            Cotizacion.objects.all().delete()
            LineaVenta.objects.all().delete()
            Venta.objects.all().delete()
            Cliente.objects.all().delete()

            # Compras
            LineaCompra.objects.all().delete()
            Compra.objects.all().delete()
            Proveedor.objects.all().delete()

            # Inventario al final: nada queda referenciándolo.
            MovimientoInventario.objects.all().delete()
            Producto.objects.all().delete()
            Categoria.objects.all().delete()

            self._reiniciar_contadores()

        self.stdout.write(self.style.SUCCESS(
            "Datos de negocio eliminados y contadores reiniciados. Usuarios, grupos de permisos y "
            "configuración de la empresa se conservaron."
        ))

    def _reiniciar_contadores(self):
        """Reinicia el autoincremento (para que el próximo registro sea #1 de nuevo)."""
        if connection.vendor == "sqlite":
            tablas = [modelo._meta.db_table for modelo in MODELOS_A_BORRAR]
            with connection.cursor() as cursor:
                placeholders = ",".join(["%s"] * len(tablas))
                cursor.execute(f"DELETE FROM sqlite_sequence WHERE name IN ({placeholders})", tablas)
        elif connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                for modelo in MODELOS_A_BORRAR:
                    tabla = modelo._meta.db_table
                    columna = modelo._meta.pk.column
                    cursor.execute(
                        "SELECT setval(pg_get_serial_sequence(%s, %s), 1, false)", [tabla, columna]
                    )
