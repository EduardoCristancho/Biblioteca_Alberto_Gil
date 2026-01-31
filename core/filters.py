import django_filters
from django.db.models import Sum

from .models import Documentos


class DocumentoFilter(django_filters.FilterSet):
    tipo_doc = django_filters.NumberFilter(field_name='id_tipo_documento')
    carrera = django_filters.NumberFilter(field_name='id_carrera')
    fecha_pub = django_filters.DateFromToRangeFilter(field_name='fecha_publicacion')
    stock_min = django_filters.NumberFilter(method='filter_stock_min')
    stock_max = django_filters.NumberFilter(method='filter_stock_max')

    class Meta:
        model = Documentos
        fields = ['tipo_doc', 'carrera', 'fecha_pub']

    def _annotated(self, qs):
        return qs.annotate(stock=Sum('ejemplares_set__unidad_fisica'))

    def filter_stock_min(self, qs, name, value):
        return self._annotated(qs).filter(stock__gte=value)

    def filter_stock_max(self, qs, name, value):
        return self._annotated(qs).filter(stock__lte=value)
