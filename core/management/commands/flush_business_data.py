from django.core.management.base import BaseCommand
from django.db import connection, transaction

from bitacora.models import ItemBitacora, Sede
from comunicaciones.models import Comunicado
from compras.models import Compra, LineaCompra, Proveedor
from documentos.models import Documento
from finanzas.models import CuentaPorCobrar, CuentaPorPagar, PagoCliente, PagoProveedor
from inventario.models import Categoria, MovimientoInventario, Producto
from produccion.models import ComponenteBOM, ComponenteOrdenProduccion, ListaMateriales, OrdenProduccion
from proyectos.models import AsignacionEmpleado, GastoProyecto, HitoProyecto, Proyecto
from rrhh.models import AbonoPrestamo, Asistencia, Departamento, DetalleNomina, Empleado, Nomina, Prestamo
from ventas.models import Cliente, Cotizacion, CuentaCobro, LineaCotizacion, LineaVenta, Venta

MODELOS_A_BORRAR = [
    Documento, Comunicado,
    ItemBitacora, Sede,
    PagoCliente, PagoProveedor, CuentaPorCobrar, CuentaPorPagar,
    AsignacionEmpleado, GastoProyecto, HitoProyecto, Proyecto,
    AbonoPrestamo, Prestamo, DetalleNomina, Nomina, Asistencia, Empleado, Departamento,
    ComponenteOrdenProduccion, OrdenProduccion, ComponenteBOM, ListaMateriales,
    CuentaCobro, LineaCotizacion, Cotizacion, LineaVenta, Venta, Cliente,
    LineaCompra, Compra, Proveedor,
    MovimientoInventario, Producto, Categoria,
]


class Command(BaseCommand):
    help = (
        "Borra todos los datos de negocio (ventas, cotizaciones, cuentas de cobro, proyectos, "
        "documentos, comunicados, compras, inventario, producción, nómina, préstamos, etc.) para "
        "dejar el sistema listo para empezar con información real. Conserva usuarios, grupos de "
        "permisos y la configuración de la empresa."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes", action="store_true",
            help="Ejecuta sin pedir confirmación interactiva.",
        )

    def handle(self, *args, **options):
        if not options["yes"]:
            respuesta = input(
                "Esto borrará TODOS los datos de negocio (ventas, compras, cotizaciones, cuentas de "
                "cobro, proyectos, documentos, comunicados, inventario, producción, nómina, préstamos, "
                "empleados, clientes, proveedores). Los usuarios, grupos de permisos y la configuración "
                "de la empresa se conservan. Escribe 'si' para continuar: "
            )
            if respuesta.strip().lower() not in ("si", "sí", "yes"):
                self.stdout.write(self.style.WARNING("Cancelado, no se borró nada."))
                return

        with transaction.atomic():
            # Documentos primero, uno por uno: el .delete() de cada instancia también
            # borra su archivo físico del almacenamiento (un .all().delete() masivo no
            # lo haría, dejaría archivos huérfanos en /media).
            for documento in Documento.objects.all():
                documento.delete()

            # Comunicaciones: independiente, sin relaciones que proteja nada.
            Comunicado.objects.all().delete()

            # Bitácora (antes de Cliente, que Sede protege, y de Cotizacion/CuentaCobro).
            ItemBitacora.objects.all().delete()
            Sede.objects.all().delete()

            # Finanzas: protegen venta/compra/nómina hasta que se borren sus pagos y cuentas.
            PagoCliente.objects.all().delete()
            PagoProveedor.objects.all().delete()
            CuentaPorCobrar.objects.all().delete()
            CuentaPorPagar.objects.all().delete()

            # Proyectos: sus hitos/gastos/asignaciones se van en cascada, pero la
            # asignación de empleado protege a Empleado, así que hay que ir antes.
            AsignacionEmpleado.objects.all().delete()
            GastoProyecto.objects.all().delete()
            HitoProyecto.objects.all().delete()
            Proyecto.objects.all().delete()

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

            # Ventas, cotizaciones y cuentas de cobro (cuenta de cobro protege al cliente).
            CuentaCobro.objects.all().delete()
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
