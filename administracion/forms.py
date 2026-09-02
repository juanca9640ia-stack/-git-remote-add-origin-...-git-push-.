from django import forms
from django.contrib.auth.models import Group, Permission, User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Q

from core.models import Empresa, PerfilUsuario


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

    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        if empresa is not None:
            # Roles compartidos de plataforma + los personalizados de esta empresa —
            # nunca los roles personalizados de otra empresa.
            self.fields["groups"].queryset = Group.objects.filter(
                Q(empresa_vinculo__isnull=True) | Q(empresa_vinculo__empresa=empresa)
            )
        for name, field in self.fields.items():
            if name == "groups":
                continue
            css = "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-control"
            field.widget.attrs.setdefault("class", css)


class EmpresaAltaForm(forms.Form):
    """Da de alta una empresa nueva en la plataforma junto con su primer usuario
    administrador. Solo la usa un superadministrador de plataforma (Fase 0.3)."""

    nombre = forms.CharField(max_length=150, label="Nombre de la empresa")
    nit = forms.CharField(max_length=30, label="NIT/Documento", required=False)
    email = forms.EmailField(label="Correo de la empresa", required=False)

    admin_username = forms.CharField(max_length=150, label="Usuario del administrador")
    admin_password1 = forms.CharField(label="Contraseña", widget=forms.PasswordInput)
    admin_password2 = forms.CharField(label="Confirmar contraseña", widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean_admin_username(self):
        username = self.cleaned_data["admin_username"].strip()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Ya existe un usuario con ese nombre en la plataforma.")
        return username

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("admin_password1"), cleaned.get("admin_password2")
        if p1 and p2:
            if p1 != p2:
                self.add_error("admin_password2", "Las contraseñas no coinciden.")
            else:
                temp_user = User(username=cleaned.get("admin_username", ""))
                try:
                    validate_password(p1, temp_user)
                except ValidationError as exc:
                    self.add_error("admin_password1", exc)
        return cleaned

    def guardar(self):
        """Crea la Empresa, su primer usuario administrador (staff, grupo
        Administración compartido) y el perfil que los vincula."""
        empresa = Empresa.objects.create(
            nombre=self.cleaned_data["nombre"],
            nit=self.cleaned_data.get("nit", ""),
            email=self.cleaned_data.get("email", ""),
        )
        admin = User.objects.create_user(
            username=self.cleaned_data["admin_username"],
            password=self.cleaned_data["admin_password1"],
            is_staff=True,
        )
        PerfilUsuario.objects.create(usuario=admin, empresa=empresa, es_superadmin_plataforma=False)
        grupo_admin = Group.objects.filter(name="Administración").first()
        if grupo_admin:
            admin.groups.add(grupo_admin)
        return empresa, admin


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


# Cada apartado define qué permisos de Django otorga al marcarlo. "apps" concede TODOS
# los permisos de esas apps (comportamiento de módulo completo, como antes). "modelos"
# concede todos los permisos de esos modelos puntuales (más fino que una app completa).
# "permisos" concede permisos individuales por su codename completo "app_label.codename"
# (para permisos personalizados que no pertenecen a un modelo de negocio, como ver el
# dashboard o registrar la propia asistencia).
APARTADOS_ROL = [
    ("dashboard", "Dashboard", {"permisos": ["core.ver_dashboard"]}),
    ("ventas", "Ventas", {"apps": ["ventas"]}),
    ("compras", "Compras", {"apps": ["compras"]}),
    ("inventario", "Inventario", {"apps": ["inventario"]}),
    ("finanzas", "Finanzas", {"apps": ["finanzas"]}),
    ("produccion", "Producción", {"apps": ["produccion"]}),
    ("rrhh_operario", "RR.HH. · Operario (su propio perfil y asistencia)", {
        "permisos": ["rrhh.marcar_propia_asistencia", "rrhh.ver_propio_perfil"],
    }),
    ("rrhh_empleados", "RR.HH. · Empleados y departamentos", {"modelos": [("rrhh", "empleado"), ("rrhh", "departamento")]}),
    ("rrhh_asistencia", "RR.HH. · Asistencia de todos los empleados", {"modelos": [("rrhh", "asistencia")]}),
    ("rrhh_nomina", "RR.HH. · Nómina", {"modelos": [("rrhh", "nomina"), ("rrhh", "detallenomina")]}),
    ("rrhh_prestamos", "RR.HH. · Préstamos", {"modelos": [("rrhh", "prestamo"), ("rrhh", "abonoprestamo")]}),
]

def permisos_de_apartado(spec):
    """Devuelve el queryset de Permission que corresponde a la definición de un apartado."""
    if "apps" in spec:
        return Permission.objects.filter(content_type__app_label__in=spec["apps"])
    if "modelos" in spec:
        query = Q()
        for app_label, modelo in spec["modelos"]:
            query |= Q(content_type__app_label=app_label, content_type__model=modelo)
        return Permission.objects.filter(query)
    if "permisos" in spec:
        query = Q()
        for permiso in spec["permisos"]:
            app_label, codename = permiso.split(".")
            query |= Q(content_type__app_label=app_label, codename=codename)
        return Permission.objects.filter(query)
    return Permission.objects.none()


class RolForm(forms.Form):
    nombre = forms.CharField(max_length=150, label="Nombre del rol")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["nombre"].widget.attrs.setdefault("class", "form-control")
        for clave, etiqueta, _spec in APARTADOS_ROL:
            self.fields[clave] = forms.BooleanField(required=False, label=etiqueta)
            self.fields[clave].widget.attrs.setdefault("class", "form-check-input")

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
