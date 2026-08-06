from django.contrib import admin

from .models import AbonoPrestamo, Asistencia, Departamento, DetalleNomina, Empleado, Nomina, Prestamo


@admin.register(Departamento)
class DepartamentoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "descripcion")
    search_fields = ("nombre",)


@admin.register(Empleado)
class EmpleadoAdmin(admin.ModelAdmin):
    list_display = (
        "nombre_completo", "documento", "cargo", "departamento",
        "tipo_pago", "salario_base", "valor_dia", "activo",
    )
    list_filter = ("departamento", "tipo_pago", "activo")
    search_fields = ("nombre_completo", "documento", "cargo")


@admin.register(Asistencia)
class AsistenciaAdmin(admin.ModelAdmin):
    list_display = ("empleado", "fecha", "estado", "hora_entrada", "hora_salida")
    list_filter = ("estado",)
    search_fields = ("empleado__nombre_completo",)
    date_hierarchy = "fecha"


class DetalleNominaInline(admin.TabularInline):
    model = DetalleNomina
    extra = 0


@admin.register(Nomina)
class NominaAdmin(admin.ModelAdmin):
    list_display = ("periodo", "estado", "total_pagar", "creado_en")
    list_filter = ("estado",)
    inlines = [DetalleNominaInline]
    readonly_fields = ("procesada_en",)


class AbonoPrestamoInline(admin.TabularInline):
    model = AbonoPrestamo
    extra = 0
    readonly_fields = ("fecha",)


@admin.register(Prestamo)
class PrestamoAdmin(admin.ModelAdmin):
    list_display = ("empleado", "monto", "saldo_pendiente", "estado", "fecha_otorgado")
    list_filter = ("estado",)
    search_fields = ("empleado__nombre_completo",)
    inlines = [AbonoPrestamoInline]
    readonly_fields = ("creado_en",)
