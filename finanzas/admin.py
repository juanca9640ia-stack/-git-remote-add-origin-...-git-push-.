from django.contrib import admin

from .models import CuentaPorCobrar, CuentaPorPagar, PagoCliente, PagoProveedor


class PagoClienteInline(admin.TabularInline):
    model = PagoCliente
    extra = 0
    readonly_fields = ("monto", "metodo", "referencia", "registrado_por", "creado_en")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CuentaPorCobrar)
class CuentaPorCobrarAdmin(admin.ModelAdmin):
    list_display = ("venta", "monto_total", "saldo_pendiente", "estado", "creado_en")
    list_filter = ("estado",)
    search_fields = ("venta__numero", "venta__cliente__nombre")
    readonly_fields = ("venta", "monto_total", "saldo_pendiente", "estado")
    inlines = [PagoClienteInline]

    def has_add_permission(self, request):
        return False


class PagoProveedorInline(admin.TabularInline):
    model = PagoProveedor
    extra = 0
    readonly_fields = ("monto", "metodo", "referencia", "registrado_por", "creado_en")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CuentaPorPagar)
class CuentaPorPagarAdmin(admin.ModelAdmin):
    list_display = ("origen", "contraparte", "monto_total", "saldo_pendiente", "estado", "creado_en")
    list_filter = ("estado",)
    search_fields = ("compra__numero", "compra__proveedor__nombre", "nomina__periodo")
    readonly_fields = ("compra", "nomina", "monto_total", "saldo_pendiente", "estado")
    inlines = [PagoProveedorInline]

    def has_add_permission(self, request):
        return False
