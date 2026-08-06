from django import forms
from django.forms import inlineformset_factory

from .models import Cliente, Cotizacion, LineaCotizacion, LineaVenta, Venta


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nombre", "documento", "email", "telefono", "direccion", "activo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-control"
            field.widget.attrs.setdefault("class", css)


class ClienteRapidoForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nombre", "documento", "telefono", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class VentaForm(forms.ModelForm):
    class Meta:
        model = Venta
        fields = ["cliente", "impuesto_porcentaje", "notas"]
        widgets = {
            "notas": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class LineaVentaForm(forms.ModelForm):
    class Meta:
        model = LineaVenta
        fields = ["producto", "cantidad", "precio_unitario"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control form-control-sm")


LineaVentaFormSet = inlineformset_factory(
    Venta, LineaVenta,
    form=LineaVentaForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


class CotizacionForm(forms.ModelForm):
    class Meta:
        model = Cotizacion
        fields = ["cliente", "impuesto_porcentaje", "fecha_validez", "sede", "notas"]
        widgets = {
            "notas": forms.Textarea(attrs={"rows": 3}),
            "fecha_validez": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class LineaCotizacionForm(forms.ModelForm):
    class Meta:
        model = LineaCotizacion
        fields = ["producto", "cantidad", "precio_unitario"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control form-control-sm")


LineaCotizacionFormSet = inlineformset_factory(
    Cotizacion, LineaCotizacion,
    form=LineaCotizacionForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)
