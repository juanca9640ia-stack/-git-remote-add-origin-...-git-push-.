from django.urls import path

from . import views

app_name = "comunicaciones"

urlpatterns = [
    path("", views.comunicado_lista, name="comunicado_lista"),
    path("<int:pk>/eliminar/", views.comunicado_eliminar, name="comunicado_eliminar"),
]
