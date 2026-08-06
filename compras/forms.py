from django import forms
from django.forms import inlineformset_factory

from .models import Compra, LineaCompra, Proveedor


class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = ["nombre", "nit", "email", "telefono", "direccion", "activo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-control"
            field.widget.attrs.setdefault("class", css)


class ProveedorRapidoForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = ["nombre", "nit", "telefono", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class CompraForm(forms.ModelForm):
    class Meta:
        model = Compra
        fields = ["proveedor", "impuesto_porcentaje", "notas"]
        widgets = {
            "notas": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class LineaCompraForm(forms.ModelForm):
    class Meta:
        model = LineaCompra
        fields = ["producto", "cantidad", "precio_unitario"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control form-control-sm")


LineaCompraFormSet = inlineformset_factory(
    Compra, LineaCompra,
    form=LineaCompraForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)
