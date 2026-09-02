from django.db import migrations


def crear_empresa_semilla(apps, schema_editor):
    """Garantiza que exista la Empresa #1 (el inquilino actual, Inversiones Jasda)
    antes de que las demás apps empiecen a exigir una FK de empresa obligatoria.
    Es la base de la Fase 0 (cimiento de datos multiempresa)."""
    Empresa = apps.get_model("core", "Empresa")
    Empresa.objects.get_or_create(pk=1)


def revertir(apps, schema_editor):
    # No se borra la empresa semilla al revertir: para entonces ya hay datos de
    # negocio reales apuntando a ella en todas las demás apps.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_alter_empresa_options"),
    ]

    operations = [
        migrations.RunPython(crear_empresa_semilla, revertir),
    ]
