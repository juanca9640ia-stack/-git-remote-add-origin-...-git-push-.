from django import forms
from django.contrib.auth import get_user_model

from rrhh.models import Empleado
from ventas.models import Cliente

from .models import AsignacionEmpleado, GastoProyecto, HitoProyecto, Proyecto

User = get_user_model()


class ProyectoForm(forms.ModelForm):
    class Meta:
        model = Proyecto
        fields = [
            "nombre", "cliente", "ubicacion", "descripcion", "estado", "presupuesto",
            "fecha_inicio", "fecha_fin_estimada", "fecha_fin_real", "responsable",
        ]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 3}),
            "fecha_inicio": forms.DateInput(attrs={"type": "date"}),
            "fecha_fin_estimada": forms.DateInput(attrs={"type": "date"}),
            "fecha_fin_real": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            css = campo.widget.attrs.get("class", "")
            campo.widget.attrs["class"] = (css + " form-select" if isinstance(campo.widget, forms.Select) else css + " form-control").strip()
        if empresa is not None:
            self.fields["cliente"].queryset = Cliente.objects.filter(empresa=empresa).order_by("nombre")
            self.fields["responsable"].queryset = User.objects.filter(
                perfil__empresa=empresa
            ).order_by("username")


class HitoForm(forms.ModelForm):
    class Meta:
        model = HitoProyecto
        fields = ["nombre", "fecha_objetivo", "orden"]
        widgets = {
            "fecha_objetivo": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "form-control"


class GastoForm(forms.ModelForm):
    class Meta:
        model = GastoProyecto
        fields = ["concepto", "categoria", "valor", "fecha"]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            css = "form-select" if isinstance(campo.widget, forms.Select) else "form-control"
            campo.widget.attrs["class"] = css


class AsignacionForm(forms.ModelForm):
    class Meta:
        model = AsignacionEmpleado
        fields = ["empleado", "rol_en_obra"]

    def __init__(self, *args, empresa=None, proyecto=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["empleado"].widget.attrs["class"] = "form-select"
        self.fields["rol_en_obra"].widget.attrs["class"] = "form-control"
        if empresa is not None:
            qs = Empleado.objects.filter(empresa=empresa, activo=True)
            if proyecto is not None:
                asignados_ids = proyecto.asignaciones.filter(activo=True).values_list("empleado_id", flat=True)
                qs = qs.exclude(pk__in=asignados_ids)
            self.fields["empleado"].queryset = qs.order_by("nombre_completo")
