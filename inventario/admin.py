from django.contrib import admin

from .models import Categoria, MovimientoInventario, Producto


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "descripcion")
    search_fields = ("nombre",)


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("sku", "nombre", "tipo", "categoria", "precio_venta", "stock_actual", "stock_minimo", "activo")
    list_filter = ("tipo", "categoria", "activo")
    search_fields = ("sku", "nombre")
    list_editable = ("precio_venta",)


@admin.register(MovimientoInventario)
class MovimientoInventarioAdmin(admin.ModelAdmin):
    list_display = ("creado_en", "producto", "tipo", "motivo", "cantidad", "stock_resultante", "referencia", "usuario")
    list_filter = ("tipo", "motivo")
    search_fields = ("producto__sku", "producto__nombre", "referencia")
    date_hierarchy = "creado_en"
    readonly_fields = [f.name for f in MovimientoInventario._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
