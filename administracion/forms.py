from django import forms
from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from core.models import Empresa


LOGO_MAX_BYTES = 2 * 1024 * 1024  # 2 MB


class EmpresaForm(forms.ModelForm):
    class Meta:
        model = Empresa
        fields = ["nombre", "nit", "direccion", "telefono", "email", "moneda", "logo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            css = "form-control" if name != "logo" else "form-control form-control-sm"
            field.widget.attrs.setdefault("class", css)

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if logo and hasattr(logo, "size") and logo.size > LOGO_MAX_BYTES:
            raise forms.ValidationError("El logo no puede superar 2 MB.")
        return logo


class UsuarioBaseForm(forms.ModelForm):
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(), required=False,
        widget=forms.CheckboxSelectMultiple, label="Grupos de permisos",
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active", "is_staff", "groups"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name == "groups":
                continue
            css = "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-control"
            field.widget.attrs.setdefault("class", css)


class UsuarioCrearForm(UsuarioBaseForm):
    password1 = forms.CharField(label="Contraseña", widget=forms.PasswordInput(attrs={"class": "form-control"}))
    password2 = forms.CharField(label="Confirmar contraseña", widget=forms.PasswordInput(attrs={"class": "form-control"}))

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2:
            if p1 != p2:
                self.add_error("password2", "Las contraseñas no coinciden.")
            else:
                temp_user = User(
                    username=cleaned.get("username", ""), email=cleaned.get("email", ""),
                    first_name=cleaned.get("first_name", ""), last_name=cleaned.get("last_name", ""),
                )
                try:
                    validate_password(p1, temp_user)
                except ValidationError as exc:
                    self.add_error("password1", exc)
        return cleaned

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.set_password(self.cleaned_data["password1"])
        if commit:
            usuario.save()
            self.save_m2m()
        return usuario


class UsuarioEditarForm(UsuarioBaseForm):
    pass


MODULOS_ROL = [
    ("ventas", "Ventas"),
    ("inventario", "Inventario"),
    ("compras", "Compras"),
    ("finanzas", "Finanzas"),
    ("produccion", "Producción"),
    ("rrhh", "RR.HH."),
]


class RolForm(forms.Form):
    nombre = forms.CharField(max_length=150, label="Nombre del rol")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["nombre"].widget.attrs.setdefault("class", "form-control")
        for app_label, etiqueta in MODULOS_ROL:
            self.fields[app_label] = forms.BooleanField(required=False, label=etiqueta)
            self.fields[app_label].widget.attrs.setdefault("class", "form-check-input")

    def clean_nombre(self):
        nombre = self.cleaned_data["nombre"].strip()
        if not nombre:
            raise forms.ValidationError("El nombre del rol es obligatorio.")
        return nombre


class CambiarPasswordForm(forms.Form):
    password1 = forms.CharField(label="Nueva contraseña", widget=forms.PasswordInput(attrs={"class": "form-control"}))
    password2 = forms.CharField(label="Confirmar contraseña", widget=forms.PasswordInput(attrs={"class": "form-control"}))

    def __init__(self, *args, usuario=None, **kwargs):
        self.usuario = usuario
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2:
            if p1 != p2:
                self.add_error("password2", "Las contraseñas no coinciden.")
            else:
                try:
                    validate_password(p1, self.usuario)
                except ValidationError as exc:
                    self.add_error("password1", exc)
        return cleaned
