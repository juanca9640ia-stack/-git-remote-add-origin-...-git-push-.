from django import forms

from .models import METODO_PAGO_CHOICES


class RegistrarPagoForm(forms.Form):
    monto = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)
    metodo = forms.ChoiceField(choices=METODO_PAGO_CHOICES)
    referencia = forms.CharField(max_length=100, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
