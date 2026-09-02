from django.db import migrations


def crear_perfiles_faltantes(apps, schema_editor):
    """Todo usuario que ya existía antes de la Fase 0 queda vinculado a la empresa
    semilla (Jasda, pk=1). Los superusuarios además quedan como superadministradores
    de la plataforma, para no perder acceso a la administración multiempresa."""
    User = apps.get_model("auth", "User")
    PerfilUsuario = apps.get_model("core", "PerfilUsuario")

    for usuario in User.objects.all():
        PerfilUsuario.objects.get_or_create(
            usuario=usuario,
            defaults={"empresa_id": 1, "es_superadmin_plataforma": usuario.is_superuser},
        )


def revertir(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_alter_empresa_options_empresa_activa_and_more"),
    ]

    operations = [
        migrations.RunPython(crear_perfiles_faltantes, revertir),
    ]
