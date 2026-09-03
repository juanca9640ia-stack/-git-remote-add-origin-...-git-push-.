from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError as ModelValidationError
from django.db.models import Sum
from django.forms import inlineformset_factory

from .models import Asistencia, Departamento, DetalleNomina, Empleado, Nomina, Prestamo, rango_periodo


class DepartamentoForm(forms.ModelForm):
    class Meta:
        model = Departamento
        fields = ["nombre", "descripcion"]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class EmpleadoForm(forms.ModelForm):
    class Meta:
        model = Empleado
        fields = [
            "nombre_completo", "documento", "cargo", "departamento",
            "email", "telefono", "fecha_contratacion", "tipo_contrato", "tipo_pago",
            "salario_base", "valor_dia", "activo",
        ]
        widgets = {
            "fecha_contratacion": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        if empresa is not None:
            self.fields["departamento"].queryset = Departamento.objects.filter(empresa=empresa)
        for field in self.fields.values():
            css = "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-control"
            field.widget.attrs.setdefault("class", css)

    def clean(self):
        cleaned_data = super().clean()
        # Un contrato de prestación de servicios siempre se paga por día: se
        # fuerza aquí (además de en el modelo) para que la validación de abajo
        # exija el campo correcto, sin importar lo que haya llegado del formulario.
        if cleaned_data.get("tipo_contrato") == Empleado.PRESTACION_SERVICIOS:
            cleaned_data["tipo_pago"] = Empleado.PAGO_DIA

        tipo_pago = cleaned_data.get("tipo_pago")
        if tipo_pago == Empleado.PAGO_SALARIO and not cleaned_data.get("salario_base"):
            self.add_error("salario_base", "Ingresa el salario base para este tipo de pago.")
        if tipo_pago == Empleado.PAGO_DIA and not cleaned_data.get("valor_dia"):
            self.add_error("valor_dia", "Ingresa el valor por día para este tipo de pago.")
        return cleaned_data


class AsistenciaForm(forms.ModelForm):
    class Meta:
        model = Asistencia
        fields = ["fecha", "estado", "hora_entrada", "hora_salida", "notas"]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "hora_entrada": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "hora_salida": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class NominaForm(forms.Form):
    periodo = forms.CharField(
        max_length=8, help_text="Mensual: AAAA-MM (ej. 2026-08). Semanal: AAAA-Www (ej. 2026-W32).",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "2026-08 o 2026-W32"}),
    )

    def __init__(self, *args, empresa=None, **kwargs):
        self.empresa = empresa
        super().__init__(*args, **kwargs)

    def clean_periodo(self):
        periodo = self.cleaned_data["periodo"].strip().upper()
        try:
            rango_periodo(periodo)
        except ModelValidationError as exc:
            raise forms.ValidationError(exc.messages[0])
        existentes = Nomina.objects.filter(periodo=periodo)
        if self.empresa is not None:
            existentes = existentes.filter(empresa=self.empresa)
        if existentes.exists():
            raise forms.ValidationError(f"Ya existe una nómina para el período {periodo}.")
        return periodo


class DetalleNominaForm(forms.ModelForm):
    class Meta:
        model = DetalleNomina
        fields = ["horas_extra", "bonificaciones", "deducciones", "descuento_prestamo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control form-control-sm")

    def clean_descuento_prestamo(self):
        valor = self.cleaned_data.get("descuento_prestamo") or Decimal("0")
        empleado_id = self.instance.empleado_id
        if valor > 0 and empleado_id:
            saldo_disponible = Prestamo.objects.filter(
                empleado_id=empleado_id, estado=Prestamo.ACTIVO,
            ).aggregate(total=Sum("saldo_pendiente"))["total"] or Decimal("0")
            if valor > saldo_disponible:
                raise forms.ValidationError(
                    f"{self.instance.empleado} no tiene saldo de préstamo suficiente "
                    f"(disponible: ${saldo_disponible})."
                )
        return valor


DetalleNominaFormSet = inlineformset_factory(
    Nomina, DetalleNomina,
    form=DetalleNominaForm,
    extra=0,
    can_delete=False,
)


class PrestamoForm(forms.ModelForm):
    class Meta:
        model = Prestamo
        fields = ["empleado", "monto", "motivo", "fecha_otorgado"]
        widgets = {
            "motivo": forms.Textarea(attrs={"rows": 2}),
            "fecha_otorgado": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        empleados = Empleado.objects.filter(activo=True)
        if empresa is not None:
            empleados = empleados.filter(empresa=empresa)
        self.fields["empleado"].queryset = empleados
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean_monto(self):
        monto = self.cleaned_data.get("monto")
        if monto is not None and monto <= 0:
            raise forms.ValidationError("El monto del préstamo debe ser mayor que cero.")
        return monto
