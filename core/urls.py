from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LoginView, LogoutView, MeView,
    UserRetrieveView, UserCreateView, UserUpdateView,
    AutorListView, AutorUpdateView,
    UbicacionViewSet, CarreraViewSet, EstadoEjemplarViewSet,
    DocumentoListCreateView, DocumentoUpdateView, DocumentoDeleteView,
    EjemplarUpdateDeleteView,
    EjemplarCreateView,
    PrestamoListCreateView, PrestamoDetailView, PrestamoConcluirView,
    AreaSugerenciaView, TutorSugerenciaView, AreaCatalogoView,
)

router = DefaultRouter()
router.register(r'ubicaciones', UbicacionViewSet, basename='ubicaciones')
router.register(r'carreras', CarreraViewSet, basename='carreras')
router.register(r'estados-ejemplar', EstadoEjemplarViewSet, basename='estados-ejemplar')

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
    path('documentos/<int:documento_id>/ejemplares', EjemplarCreateView.as_view()),  # POST crear ejemplar

    # Ejemplares
    path('ejemplares/<int:ejemplar_id>', EjemplarUpdateDeleteView.as_view()),  # PATCH, DELETE

    # Sugerencias (combobox)
    path('sugerencias/areas', AreaSugerenciaView.as_view()),
    path('sugerencias/tutores', TutorSugerenciaView.as_view()),
    path('areas/', AreaCatalogoView.as_view()),

    # Prestamos
    path('prestamo', PrestamoListCreateView.as_view()),  # GET list + POST create
    path('prestamo/<int:prestamo_id>', PrestamoDetailView.as_view()),  # PUT update ejemplares/fecha_vencimiento, DELETE cancela
    path('prestamo/<int:prestamo_id>/concluir', PrestamoConcluirView.as_view()),  # POST concluir préstamo

    # Routers
    path('', include(router.urls)),
]
