from django import forms
from .models import Estimate, EstimateSection, EstimateItem, Nomenclature, NomenclatureGroup, NomenclatureAlias


class EstimateImportForm(forms.Form):
    file = forms.FileField(
        label='Excel файл сметы',
        help_text='Поддерживаются форматы .xlsx и .xls'
    )

    def clean_file(self):
        f = self.cleaned_data['file']
        ext = f.name.rsplit('.', 1)[-1].lower()
        if ext not in ('xlsx', 'xls'):
            raise forms.ValidationError('Допустимые форматы: .xlsx, .xls')
        return f


class EstimateItemForm(forms.ModelForm):
    class Meta:
        model = EstimateItem
        fields = ['name', 'nomenclature', 'unit', 'quantity', 'unit_price', 'total_amount', 'note']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'nomenclature': forms.Select(attrs={'class': 'form-select'}),
            'unit': forms.TextInput(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'total_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'note': forms.TextInput(attrs={'class': 'form-control'}),
        }


class EstimateSectionForm(forms.ModelForm):
    class Meta:
        model = EstimateSection
        fields = ['name', 'code', 'parent', 'order']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Например: 5.1'}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, estimate, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parent'].queryset = EstimateSection.objects.filter(estimate=estimate)
        self.fields['parent'].required = False


class NomenclatureForm(forms.ModelForm):
    class Meta:
        model = Nomenclature
        fields = ['name', 'code_1c', 'unit', 'group', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code_1c': forms.TextInput(attrs={'class': 'form-control'}),
            'unit': forms.TextInput(attrs={'class': 'form-control'}),
            'group': forms.Select(attrs={'class': 'form-select'}),
        }
