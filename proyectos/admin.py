from django.contrib import admin

from .models import AsignacionEmpleado, GastoProyecto, HitoProyecto, Proyecto


class HitoProyectoInline(admin.TabularInline):
    model = HitoProyecto
    extra = 0


class GastoProyectoInline(admin.TabularInline):
    model = GastoProyecto
    extra = 0


class AsignacionEmpleadoInline(admin.TabularInline):
    model = AsignacionEmpleado
    extra = 0


@admin.register(Proyecto)
class ProyectoAdmin(admin.ModelAdmin):
    list_display = ("numero", "nombre", "estado", "presupuesto", "empresa")
    search_fields = ("numero", "nombre")
    list_filter = ("estado", "empresa")
    inlines = [HitoProyectoInline, GastoProyectoInline, AsignacionEmpleadoInline]
