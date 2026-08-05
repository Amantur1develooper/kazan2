from django import forms
from apps.projects.models import ResidentialComplex, Block
from .models import DDSImport


class DDSImportForm(forms.Form):
    residential_complex = forms.ModelChoiceField(
        queryset=ResidentialComplex.objects.all(),
        label='ЖК',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_residential_complex'}),
    )
    block = forms.ModelChoiceField(
        queryset=Block.objects.select_related('residential_complex').order_by('residential_complex__name', 'name'),
        label='Блок',
        required=False,
        empty_label='— Все записи (без конкретного блока) —',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_block'}),
    )
    file = forms.FileField(
        label='Файл ДДС (Excel)',
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.xls,.xlsx'}),
    )
