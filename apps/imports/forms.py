from django import forms
from .models import ExcelImport
from apps.projects.models import Organization, ResidentialComplex, Block, Stage, Floor


class FloorSelectForm(forms.Form):
    """Step 1: select target floor before uploading file."""
    organization = forms.ModelChoiceField(
        queryset=Organization.objects.all(),
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_org'}),
        label='Организация',
        empty_label='— выберите организацию —',
    )
    complex = forms.ModelChoiceField(
        queryset=ResidentialComplex.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_complex'}),
        label='Жилой комплекс',
        empty_label='— выберите ЖК —',
    )
    block = forms.ModelChoiceField(
        queryset=Block.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_block'}),
        label='Блок',
        empty_label='— выберите блок —',
    )
    stage = forms.ModelChoiceField(
        queryset=Stage.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_stage'}),
        label='Этап',
        empty_label='— выберите этап —',
    )
    floor = forms.ModelChoiceField(
        queryset=Floor.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_floor'}),
        label='Этаж',
        empty_label='— выберите этаж —',
        required=False,
    )
    new_floor_number = forms.IntegerField(
        required=False, min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'или введите новый номер'}),
        label='Создать новый этаж (номер)',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'organization' in self.data:
            try:
                org_id = int(self.data.get('organization'))
                self.fields['complex'].queryset = ResidentialComplex.objects.filter(organization_id=org_id)
            except (ValueError, TypeError):
                pass
        if 'complex' in self.data:
            try:
                cx_id = int(self.data.get('complex'))
                self.fields['block'].queryset = Block.objects.filter(residential_complex_id=cx_id)
            except (ValueError, TypeError):
                pass
        if 'block' in self.data:
            try:
                bl_id = int(self.data.get('block'))
                self.fields['stage'].queryset = Stage.objects.filter(block_id=bl_id)
            except (ValueError, TypeError):
                pass
        if 'stage' in self.data:
            try:
                st_id = int(self.data.get('stage'))
                self.fields['floor'].queryset = Floor.objects.filter(stage_id=st_id)
            except (ValueError, TypeError):
                pass

    def clean(self):
        cleaned = super().clean()
        floor = cleaned.get('floor')
        new_num = cleaned.get('new_floor_number')
        stage = cleaned.get('stage')

        if not floor and not new_num:
            self.add_error('floor', 'Выберите существующий этаж или введите номер нового.')
        if new_num and stage:
            if Floor.objects.filter(stage=stage, number=new_num).exists():
                self.add_error('new_floor_number',
                               f'Этаж {new_num} уже существует в этом этапе. Выберите его выше.')
        return cleaned


class ExcelImportForm(forms.ModelForm):
    class Meta:
        model = ExcelImport
        fields = ['file', 'import_mode', 'notes']
        widgets = {
            'file': forms.FileInput(attrs={'class': 'form-control', 'accept': '.xlsx,.xls'}),
            'import_mode': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
        labels = {
            'file': 'Excel файл (.xlsx, .xls)',
            'import_mode': 'Режим при повторной загрузке',
            'notes': 'Заметки',
        }

    def clean_file(self):
        f = self.cleaned_data.get('file')
        if f:
            ext = f.name.rsplit('.', 1)[-1].lower()
            if ext not in ('xlsx', 'xls'):
                raise forms.ValidationError('Допустимы только .xlsx или .xls')
        return f
