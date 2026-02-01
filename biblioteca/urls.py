from django.contrib import admin
from django.urls import path, include
from core import views as web_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('core.urls')),
    # Web pages
    path('', web_views.dashboard_page, name='dashboard'),
    path('login/', web_views.login_page, name='login'),
    path('logout/', web_views.logout_page, name='logout'),
    path('inventario/', web_views.inventario_gestion_page, name='gestion_inventario'),
    path('inventario/registrar/', web_views.inventario_registrar_page, name='registrar_inventario'),
    path('inventario/registrar/libro/', web_views.inventario_registrar_libro_page, name='registrar_libro'),
    path('inventario/registrar/tesis/', web_views.inventario_registrar_tesis_page, name='registrar_tesis'),
    path('prestamos/', web_views.prestamos_gestion_page, name='gestion_prestamos'),
    path('prestamos/registrar/', web_views.prestamos_registrar_page, name='registrar_prestamos'),
    path('usuarios/', web_views.usuarios_gestion_page, name='gestion_usuarios'),
]
