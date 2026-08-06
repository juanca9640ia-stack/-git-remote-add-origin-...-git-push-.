from django.contrib import admin

from .models import Cliente, Cotizacion, LineaCotizacion, LineaVenta, Venta


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nombre", "documento", "email", "telefono", "activo")
    search_fields = ("nombre", "documento", "email")
    list_filter = ("activo",)


class LineaVentaInline(admin.TabularInline):
    model = LineaVenta
    extra = 1


@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ("numero", "cliente", "estado", "total", "vendedor", "creado_en")
    list_filter = ("estado",)
    search_fields = ("numero", "cliente__nombre")
    date_hierarchy = "creado_en"
    inlines = [LineaVentaInline]
    readonly_fields = ("numero", "confirmada_en")


class LineaCotizacionInline(admin.TabularInline):
    model = LineaCotizacion
    extra = 1


@admin.register(Cotizacion)
class CotizacionAdmin(admin.ModelAdmin):
    list_display = ("numero", "cliente", "estado", "total", "fecha_validez", "vendedor", "creado_en")
    list_filter = ("estado",)
    search_fields = ("numero", "cliente__nombre")
    date_hierarchy = "creado_en"
    inlines = [LineaCotizacionInline]
    readonly_fields = ("numero", "enviada_en", "venta")
