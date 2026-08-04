from django import forms
from apps.projects.models import ResidentialComplex
from .models import DDSImport


class DDSImportForm(forms.Form):
    residential_complex = forms.ModelChoiceField(
        queryset=ResidentialComplex.objects.all(),
        label='ЖК',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    file = forms.FileField(
        label='Файл ДДС (Excel)',
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.xls,.xlsx'}),
    )
