from django.urls import path

from . import views

app_name = "finanzas"

urlpatterns = [
    path("", views.resumen, name="resumen"),
    path("cuentas-por-cobrar/", views.cxc_lista, name="cxc_lista"),
    path("cuentas-por-cobrar/<int:pk>/", views.cxc_detalle, name="cxc_detalle"),
    path("cuentas-por-pagar/", views.cxp_lista, name="cxp_lista"),
    path("cuentas-por-pagar/<int:pk>/", views.cxp_detalle, name="cxp_detalle"),
]
