from django.core.management import call_command
from django.core.management.base import BaseCommand

from compras.models import Proveedor
from inventario.models import Categoria, Producto
from produccion.models import ComponenteBOM, ListaMateriales
from rrhh.models import Departamento, Empleado
from ventas.models import Cliente


class Command(BaseCommand):
    help = (
        "Crea grupos de permisos y datos de ejemplo (categorías, productos, clientes). "
        "Solo para desarrollo local/demo: los datos de ejemplo NO deben correrse en producción, "
        "usa 'crear_grupos_permisos' + 'crear_admin_inicial' para eso."
    )

    def handle(self, *args, **options):
        self._crear_grupos()
        self._crear_datos_ejemplo()
        self.stdout.write(self.style.SUCCESS("Datos de ejemplo y grupos creados correctamente."))

    def _crear_grupos(self):
        call_command("crear_grupos_permisos")

    def _crear_datos_ejemplo(self):
        if Producto.objects.exists():
            self.stdout.write("Ya existen productos, se omite la carga de productos/categorías.")
        else:
            self._crear_productos()

        if Cliente.objects.exists():
            self.stdout.write("Ya existen clientes, se omite su carga.")
        else:
            self._crear_clientes()

        if Proveedor.objects.exists():
            self.stdout.write("Ya existen proveedores, se omite su carga.")
        else:
            self._crear_proveedores()

        if ListaMateriales.objects.exists():
            self.stdout.write("Ya existe una lista de materiales, se omite su carga.")
        else:
            self._crear_receta_ejemplo()

        if Empleado.objects.exists():
            self.stdout.write("Ya existen empleados, se omite su carga.")
        else:
            self._crear_empleados_ejemplo()

    def _crear_productos(self):
        cat_general, _ = Categoria.objects.get_or_create(nombre="General")
        cat_electronica, _ = Categoria.objects.get_or_create(nombre="Electrónica")

        productos = [
            dict(sku="PRD-001", nombre="Cuaderno profesional", categoria=cat_general,
                 precio_costo=1.50, precio_venta=3.00, stock_actual=100, stock_minimo=20),
            dict(sku="PRD-002", nombre="Bolígrafo azul", categoria=cat_general,
                 precio_costo=0.20, precio_venta=0.60, stock_actual=300, stock_minimo=50),
            dict(sku="PRD-003", nombre="Audífonos bluetooth", categoria=cat_electronica,
                 precio_costo=12.00, precio_venta=25.00, stock_actual=15, stock_minimo=10),
            dict(sku="PRD-004", nombre="Cargador USB-C", categoria=cat_electronica,
                 precio_costo=4.00, precio_venta=9.99, stock_actual=8, stock_minimo=10),
        ]
        for datos in productos:
            Producto.objects.get_or_create(sku=datos["sku"], defaults=datos)
        self.stdout.write("Categorías y productos de ejemplo creados.")

    def _crear_clientes(self):
        clientes = [
            dict(nombre="Cliente Mostrador", documento="", email=""),
            dict(nombre="Comercial Andina S.A.S.", documento="900123456-1", email="compras@andina.com"),
        ]
        for datos in clientes:
            Cliente.objects.get_or_create(nombre=datos["nombre"], defaults=datos)
        self.stdout.write("Clientes de ejemplo creados.")

    def _crear_proveedores(self):
        proveedores = [
            dict(nombre="Papelería Central", nit="800111222-3", email="ventas@papeleriacentral.com"),
            dict(nombre="Distribuidora TecnoImport", nit="900333444-5", email="pedidos@tecnoimport.com"),
        ]
        for datos in proveedores:
            Proveedor.objects.get_or_create(nombre=datos["nombre"], defaults=datos)
        self.stdout.write("Proveedores de ejemplo creados.")

    def _crear_receta_ejemplo(self):
        cat_general, _ = Categoria.objects.get_or_create(nombre="General")

        insumo, _ = Producto.objects.get_or_create(
            sku="PRD-005",
            defaults=dict(
                nombre="Tela de algodón (metro)", categoria=cat_general,
                precio_costo=3.00, precio_venta=0, stock_actual=200, stock_minimo=20,
            ),
        )
        terminado, _ = Producto.objects.get_or_create(
            sku="PRD-006",
            defaults=dict(
                nombre="Camiseta básica", categoria=cat_general,
                precio_costo=8.00, precio_venta=20.00, stock_actual=0, stock_minimo=5,
            ),
        )
        lista = ListaMateriales.objects.create(producto=terminado)
        ComponenteBOM.objects.create(lista=lista, insumo=insumo, cantidad_por_unidad=2)
        self.stdout.write("Receta de ejemplo creada: Camiseta básica (2 metros de tela por unidad).")

    def _crear_empleados_ejemplo(self):
        dep_ventas, _ = Departamento.objects.get_or_create(nombre="Ventas")
        dep_operaciones, _ = Departamento.objects.get_or_create(nombre="Operaciones")

        empleados = [
            dict(nombre_completo="Laura Gómez", documento="1001234567", cargo="Vendedora",
                 departamento=dep_ventas, email="laura.gomez@empresa.com", salario_base=1500000),
            dict(nombre_completo="Carlos Ramírez", documento="1009876543", cargo="Encargado de bodega",
                 departamento=dep_operaciones, email="carlos.ramirez@empresa.com", salario_base=1400000),
        ]
        for datos in empleados:
            Empleado.objects.get_or_create(documento=datos["documento"], defaults=datos)
        self.stdout.write("Empleados de ejemplo creados.")
