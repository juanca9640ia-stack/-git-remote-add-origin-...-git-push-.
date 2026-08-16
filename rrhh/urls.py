from django.urls import path

from . import views

app_name = "rrhh"

urlpatterns = [
    path("", views.resumen, name="resumen"),
    path("mi-perfil/", views.mi_perfil, name="mi_perfil"),
    path("mi-perfil/entrada/", views.mi_perfil_marcar_entrada, name="mi_perfil_marcar_entrada"),
    path("mi-perfil/salida/", views.mi_perfil_marcar_salida, name="mi_perfil_marcar_salida"),
    path("departamentos/", views.departamento_lista, name="departamento_lista"),
    path("empleados/", views.empleado_lista, name="empleado_lista"),
    path("empleados/nuevo/", views.empleado_form, name="empleado_crear"),
    path("empleados/<int:pk>/", views.empleado_detalle, name="empleado_detalle"),
    path("empleados/<int:pk>/editar/", views.empleado_form, name="empleado_editar"),
    path("asistencia/", views.asistencia_lista, name="asistencia_lista"),
    path("asistencia/<int:empleado_id>/entrada/", views.asistencia_marcar_entrada, name="asistencia_marcar_entrada"),
    path("asistencia/<int:empleado_id>/salida/", views.asistencia_marcar_salida, name="asistencia_marcar_salida"),
    path("asistencia/<int:empleado_id>/registrar/", views.asistencia_registrar, name="asistencia_registrar"),
    path("nomina/", views.nomina_lista, name="nomina_lista"),
    path("nomina/nueva/", views.nomina_crear, name="nomina_crear"),
    path("nomina/<int:pk>/", views.nomina_detalle, name="nomina_detalle"),
    path("nomina/<int:pk>/procesar/", views.nomina_procesar, name="nomina_procesar"),
    path("nomina/detalles/<int:pk>/recibo/", views.detalle_nomina_recibo, name="detalle_nomina_recibo"),
    path("prestamos/", views.prestamo_lista, name="prestamo_lista"),
    path("prestamos/nuevo/", views.prestamo_crear, name="prestamo_crear"),
    path("prestamos/<int:pk>/", views.prestamo_detalle, name="prestamo_detalle"),
]
