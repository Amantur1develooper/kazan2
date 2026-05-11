from django import forms
from .models import CashTransaction


class CashTransactionForm(forms.ModelForm):
    class Meta:
        model = CashTransaction
        fields = ['transaction_type', 'amount', 'description', 'date']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'transaction_type': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'transaction_type': 'Тип операции',
            'amount': 'Сумма',
            'description': 'Описание',
            'date': 'Дата',
        }
