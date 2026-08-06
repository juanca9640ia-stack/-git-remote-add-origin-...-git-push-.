from django.contrib import admin

from .models import Compra, LineaCompra, Proveedor


@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "nit", "email", "telefono", "activo")
    search_fields = ("nombre", "nit", "email")
    list_filter = ("activo",)


class LineaCompraInline(admin.TabularInline):
    model = LineaCompra
    extra = 1


@admin.register(Compra)
class CompraAdmin(admin.ModelAdmin):
    list_display = ("numero", "proveedor", "estado", "total", "responsable", "creado_en")
    list_filter = ("estado",)
    search_fields = ("numero", "proveedor__nombre")
    date_hierarchy = "creado_en"
    inlines = [LineaCompraInline]
    readonly_fields = ("numero", "confirmada_en")
