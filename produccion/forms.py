from django import forms
from django.forms import inlineformset_factory

from inventario.models import Producto

from .models import ComponenteBOM, ListaMateriales, OrdenProduccion


class ListaMaterialesForm(forms.ModelForm):
    class Meta:
        model = ListaMateriales
        fields = ["producto", "notas"]
        widgets = {
            "notas": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        if empresa is not None:
            self.fields["producto"].queryset = Producto.objects.filter(empresa=empresa)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        if self.instance.pk:
            self.fields["producto"].disabled = True


class ComponenteBOMForm(forms.ModelForm):
    class Meta:
        model = ComponenteBOM
        fields = ["insumo", "cantidad_por_unidad"]

    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        if empresa is not None:
            self.fields["insumo"].queryset = Producto.objects.filter(empresa=empresa)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control form-control-sm")


ComponenteBOMFormSet = inlineformset_factory(
    ListaMateriales, ComponenteBOM,
    form=ComponenteBOMForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


class OrdenProduccionForm(forms.ModelForm):
    class Meta:
        model = OrdenProduccion
        fields = ["producto", "cantidad", "notas"]
        widgets = {
            "notas": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        productos = Producto.objects.filter(lista_materiales__isnull=False, activo=True)
        if empresa is not None:
            productos = productos.filter(empresa=empresa)
        self.fields["producto"].queryset = productos
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
