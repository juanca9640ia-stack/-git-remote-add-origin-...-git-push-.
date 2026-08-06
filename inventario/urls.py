from django.urls import path

from . import views

app_name = "inventario"

urlpatterns = [
    path("productos/", views.producto_lista, name="producto_lista"),
    path("productos/nuevo/", views.producto_form, name="producto_crear"),
    path("productos/nuevo-rapido/", views.producto_crear_rapido, name="producto_crear_rapido"),
    path("productos/<int:pk>/", views.producto_detalle, name="producto_detalle"),
    path("productos/<int:pk>/editar/", views.producto_form, name="producto_editar"),
    path("productos/<int:pk>/ajustar/", views.producto_ajustar_stock, name="producto_ajustar"),
    path("servicios/", views.servicio_lista, name="servicio_lista"),
    path("categorias/", views.categoria_lista, name="categoria_lista"),
    path("movimientos/", views.movimiento_lista, name="movimiento_lista"),
]
