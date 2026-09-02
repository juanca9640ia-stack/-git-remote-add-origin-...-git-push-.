from django import forms

from .models import Comunicado


class ComunicadoForm(forms.ModelForm):
    class Meta:
        model = Comunicado
        fields = ["titulo", "cuerpo", "fijado"]
        widgets = {
            "cuerpo": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["titulo"].widget.attrs["class"] = "form-control"
        self.fields["cuerpo"].widget.attrs["class"] = "form-control"
