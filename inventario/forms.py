from decimal import Decimal

from django import forms

from .models import Categoria, MovimientoInventario, Producto


class ProductoForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = [
            "sku", "nombre", "descripcion", "tipo", "categoria",
            "precio_costo", "precio_venta", "stock_actual", "stock_minimo", "activo",
        ]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        if empresa is not None:
            self.fields["categoria"].queryset = Categoria.objects.filter(empresa=empresa)
        for field in self.fields.values():
            css = "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-control"
            field.widget.attrs.setdefault("class", css)
        if self.instance.pk:
            self.fields["stock_actual"].disabled = True
            self.fields["stock_actual"].help_text = "Usa un ajuste de inventario para modificar el stock."


class ProductoRapidoForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = [
            "sku", "nombre", "descripcion", "tipo",
            "precio_costo", "precio_venta", "stock_actual", "stock_minimo",
        ]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sku"].required = False
        self.fields["precio_costo"].required = False
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean_precio_costo(self):
        return self.cleaned_data.get("precio_costo") or Decimal("0")

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("tipo") == Producto.SERVICIO:
            cleaned_data["stock_actual"] = 0
            cleaned_data["stock_minimo"] = 0
        return cleaned_data


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nombre", "descripcion"]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class AjusteInventarioForm(forms.Form):
    tipo = forms.ChoiceField(choices=MovimientoInventario.TIPO_CHOICES)
    cantidad = forms.IntegerField(min_value=1)
    referencia = forms.CharField(max_length=100, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
