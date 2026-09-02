from django import forms

from proyectos.models import Proyecto
from ventas.models import Cliente

from .models import Documento


class DocumentoForm(forms.ModelForm):
    class Meta:
        model = Documento
        fields = ["titulo", "categoria", "archivo", "proyecto", "cliente", "descripcion"]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        for nombre, campo in self.fields.items():
            if nombre == "archivo":
                campo.widget.attrs["class"] = "form-control"
                continue
            css = "form-select" if isinstance(campo.widget, forms.Select) else "form-control"
            campo.widget.attrs["class"] = css
        self.fields["proyecto"].required = False
        self.fields["cliente"].required = False
        if empresa is not None:
            self.fields["proyecto"].queryset = Proyecto.objects.filter(empresa=empresa).order_by("-creado_en")
            self.fields["cliente"].queryset = Cliente.objects.filter(empresa=empresa).order_by("nombre")
