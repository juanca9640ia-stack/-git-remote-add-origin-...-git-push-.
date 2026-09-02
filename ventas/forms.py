from django import forms
from django.forms import inlineformset_factory

from inventario.models import Producto
from proyectos.models import Proyecto

from .models import Cliente, Cotizacion, CuentaCobro, LineaCotizacion, LineaVenta, Venta


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
        # El IVA de toda factura es 19% fijo: no se expone en el formulario normal
        # (solo un administrador podría cambiarlo desde /admin/, si alguna vez hace falta).
        fields = ["cliente", "proyecto", "notas"]
        widgets = {
            "notas": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["proyecto"].required = False
        if empresa is not None:
            self.fields["cliente"].queryset = Cliente.objects.filter(empresa=empresa)
            self.fields["proyecto"].queryset = Proyecto.objects.filter(empresa=empresa).order_by("-creado_en")
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class LineaVentaForm(forms.ModelForm):
    class Meta:
        model = LineaVenta
        fields = ["producto", "cantidad", "precio_unitario"]

    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        if empresa is not None:
            self.fields["producto"].queryset = Producto.objects.filter(empresa=empresa)
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

    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        if empresa is not None:
            self.fields["cliente"].queryset = Cliente.objects.filter(empresa=empresa)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class LineaCotizacionForm(forms.ModelForm):
    class Meta:
        model = LineaCotizacion
        fields = ["producto", "cantidad", "precio_unitario"]

    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        if empresa is not None:
            self.fields["producto"].queryset = Producto.objects.filter(empresa=empresa)
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


class CuentaCobroForm(forms.ModelForm):
    class Meta:
        model = CuentaCobro
        fields = [
            "cliente", "proyecto", "venta", "emisor_tipo", "emisor_nombre", "emisor_documento",
            "concepto", "valor", "fecha", "forma_pago", "datos_pago",
        ]
        widgets = {
            "concepto": forms.Textarea(attrs={"rows": 3}),
            "fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["venta"].required = False
        self.fields["proyecto"].required = False
        ventas_confirmadas = Venta.objects.filter(estado=Venta.CONFIRMADA)
        proyectos = Proyecto.objects.all()
        if empresa is not None:
            self.fields["cliente"].queryset = Cliente.objects.filter(empresa=empresa)
            ventas_confirmadas = ventas_confirmadas.filter(empresa=empresa)
            proyectos = proyectos.filter(empresa=empresa)
        self.fields["venta"].queryset = ventas_confirmadas.order_by("-creado_en")
        self.fields["proyecto"].queryset = proyectos.order_by("-creado_en")
        for field in self.fields.values():
            css = "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-control"
            field.widget.attrs.setdefault("class", css)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("emisor_tipo") == CuentaCobro.PERSONA_NATURAL:
            if not cleaned.get("emisor_nombre") or not cleaned.get("emisor_documento"):
                raise forms.ValidationError(
                    "Ingresa el nombre y la cédula de la persona natural que emite la cuenta de cobro."
                )
        return cleaned
