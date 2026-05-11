from django import forms
from .models import Organization, ResidentialComplex, Block, Stage, Floor, FloorExpense


class OrganizationForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class ResidentialComplexForm(forms.ModelForm):
    class Meta:
        model = ResidentialComplex
        fields = ['organization', 'name', 'total_planned_cost', 'status', 'start_date', 'end_date', 'description']
        widgets = {
            'organization': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'total_planned_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class BlockForm(forms.ModelForm):
    class Meta:
        model = Block
        fields = ['name', 'total_budget', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Например: А, Б, В или Секция 1'}),
            'total_budget': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class StageForm(forms.ModelForm):
    class Meta:
        model = Stage
        fields = ['name', 'planned_expenses', 'actual_expenses', 'order', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'planned_expenses': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'actual_expenses': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'order': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class FloorForm(forms.ModelForm):
    class Meta:
        model = Floor
        fields = ['number', 'name', 'description']
        widgets = {
            'number': forms.NumberInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Необязательно (напр. Цокольный)'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class FloorExpenseForm(forms.ModelForm):
    class Meta:
        model = FloorExpense
        fields = ['item_code', 'name', 'unit', 'quantity', 'unit_price', 'total_amount']
        widgets = {
            'item_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'НФ-00000130'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'шт, м², кг…'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'id': 'id_unit_price'}),
            'total_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'id': 'id_total_amount'}),
        }
        labels = {
            'item_code': 'Код (из 1С)',
            'name': 'Наименование',
            'unit': 'Ед. измерения',
            'quantity': 'Количество',
            'unit_price': 'Цена за единицу',
            'total_amount': 'Сумма',
        }
