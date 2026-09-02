from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from core.views import busqueda_global, dashboard, notificaciones

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', dashboard, name='dashboard'),
    path('buscar/', busqueda_global, name='busqueda_global'),
    path('notificaciones/', notificaciones, name='notificaciones'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('inventario/', include('inventario.urls')),
    path('ventas/', include('ventas.urls')),
    path('compras/', include('compras.urls')),
    path('finanzas/', include('finanzas.urls')),
    path('produccion/', include('produccion.urls')),
    path('rrhh/', include('rrhh.urls')),
    path('proyectos/', include('proyectos.urls')),
    path('administracion/', include('administracion.urls')),
]

# whitenoise sirve los estáticos (CSS/JS) pero no los archivos subidos por el
# usuario (ej. logo de la empresa); sin este servidor no habría forma de verlos
# en producción, ya que no usamos un bucket externo (S3/Cloudinary) todavía.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
