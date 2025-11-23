from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LoginView, LogoutView, MeView,
    UserRetrieveView, UserCreateView, UserUpdateView,
    AutorListView, AutorUpdateView,
    UbicacionViewSet, CarreraViewSet,
    DocumentoListCreateView, DocumentoUpdateView, DocumentoDeleteView,
)

router = DefaultRouter()
router.register(r'ubicaciones', UbicacionViewSet, basename='ubicaciones')
router.register(r'carreras', CarreraViewSet, basename='carreras')

urlpatterns = [
    # Auth
    path('auth/login', LoginView.as_view()),
    path('auth/logout', LogoutView.as_view()),
    path('auth/me', MeView.as_view()),

    # Users
    path('users/<int:id>', UserRetrieveView.as_view()),
    path('users/', UserCreateView.as_view()),
    path('users/<int:id>/patch', UserUpdateView.as_view()),

    # Autores
    path('autores/', AutorListView.as_view()),
    path('autores/<int:pk>', AutorUpdateView.as_view()),

    # Documentos
    path('documentos/', DocumentoListCreateView.as_view()),  # GET list + POST create
    path('documentos/<int:pk>', DocumentoUpdateView.as_view()),  # PATCH
    path('documentos/<int:pk>/delete', DocumentoDeleteView.as_view()),  # soft delete

    # Routers
    path('', include(router.urls)),
]
