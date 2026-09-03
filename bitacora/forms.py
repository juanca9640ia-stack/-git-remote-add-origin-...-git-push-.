from django import forms

from ventas.models import Cliente

from .models import ItemBitacora, Sede


class SedeForm(forms.ModelForm):
    class Meta:
        model = Sede
        fields = ["cliente", "nombre", "direccion", "activa"]

    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        if empresa is not None:
            self.fields["cliente"].queryset = Cliente.objects.filter(empresa=empresa).order_by("nombre")
        for field in self.fields.values():
            css = "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-control"
            field.widget.attrs.setdefault("class", css)


class ItemBitacoraForm(forms.ModelForm):
    class Meta:
        model = ItemBitacora
        fields = ["fecha", "descripcion", "unidad", "cantidad", "valor_unitario", "notas"]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notas": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
