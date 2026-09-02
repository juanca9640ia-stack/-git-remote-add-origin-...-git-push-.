from django.urls import path

from . import views

app_name = "proyectos"

urlpatterns = [
    path("", views.proyecto_lista, name="proyecto_lista"),
    path("nuevo/", views.proyecto_form, name="proyecto_crear"),
    path("<int:pk>/", views.proyecto_detalle, name="proyecto_detalle"),
    path("<int:pk>/editar/", views.proyecto_form, name="proyecto_editar"),
    path("<int:pk>/hitos/nuevo/", views.hito_crear, name="hito_crear"),
    path("<int:pk>/hitos/<int:hito_pk>/toggle/", views.hito_toggle, name="hito_toggle"),
    path("<int:pk>/hitos/<int:hito_pk>/eliminar/", views.hito_eliminar, name="hito_eliminar"),
    path("<int:pk>/gastos/nuevo/", views.gasto_crear, name="gasto_crear"),
    path("<int:pk>/gastos/<int:gasto_pk>/eliminar/", views.gasto_eliminar, name="gasto_eliminar"),
    path("<int:pk>/asignaciones/nueva/", views.asignacion_crear, name="asignacion_crear"),
    path("<int:pk>/asignaciones/<int:asignacion_pk>/quitar/", views.asignacion_quitar, name="asignacion_quitar"),
]
