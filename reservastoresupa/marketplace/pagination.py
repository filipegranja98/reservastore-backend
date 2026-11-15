from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.utils.urls import replace_query_param


class OptionalPageNumberPagination(PageNumberPagination):
    """Opt in without breaking existing clients that expect a plain list."""
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    last_page_strings = ()

    def paginate_queryset(self, queryset, request, view=None):
        if not {self.page_query_param, self.page_size_query_param}.intersection(request.query_params):
            return None
        return super().paginate_queryset(queryset, request, view=view)

    def get_page_size(self, request):
        raw = request.query_params.get(self.page_size_query_param)
        if raw is None:
            return self.page_size
        try:
            size = int(raw)
        except (TypeError, ValueError):
            raise ValidationError({"page_size": "Informe um inteiro entre 1 e 100."})
        if not 1 <= size <= self.max_page_size:
            raise ValidationError({"page_size": "Informe um inteiro entre 1 e 100."})
        return size

    def get_previous_link(self):
        if not self.page.has_previous():
            return None
        # Keep page=1, otherwise an opt-in client could receive a plain list on back navigation.
        return replace_query_param(self.request.build_absolute_uri(), self.page_query_param, self.page.previous_page_number())
