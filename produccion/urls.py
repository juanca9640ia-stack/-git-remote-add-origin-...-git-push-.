from django.urls import path

from . import views

app_name = "produccion"

urlpatterns = [
    path("recetas/", views.bom_lista, name="bom_lista"),
    path("recetas/nueva/", views.bom_crear, name="bom_crear"),
    path("recetas/<int:pk>/editar/", views.bom_editar, name="bom_editar"),
    path("ordenes/", views.orden_lista, name="orden_lista"),
    path("ordenes/nueva/", views.orden_crear, name="orden_crear"),
    path("ordenes/<int:pk>/", views.orden_detalle, name="orden_detalle"),
    path("ordenes/<int:pk>/editar/", views.orden_editar, name="orden_editar"),
    path("ordenes/<int:pk>/completar/", views.orden_completar, name="orden_completar"),
    path("ordenes/<int:pk>/anular/", views.orden_anular, name="orden_anular"),
]
