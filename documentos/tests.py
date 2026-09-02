import shutil
import tempfile
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Empresa, PerfilUsuario
from proyectos.models import Proyecto
from ventas.models import Cliente

from .models import Documento

MEDIA_ROOT_TEMPORAL = tempfile.mkdtemp()


def _archivo_prueba(nombre="contrato.pdf", contenido=b"contenido de prueba"):
    return SimpleUploadedFile(nombre, contenido, content_type="application/pdf")


@override_settings(MEDIA_ROOT=MEDIA_ROOT_TEMPORAL)
class DocumentoModelTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT_TEMPORAL, ignore_errors=True)

    def test_tamano_bytes_se_calcula_al_guardar(self):
        doc = Documento.objects.create(titulo="Contrato de obra", archivo=_archivo_prueba())
        self.assertEqual(doc.tamano_bytes, len(b"contenido de prueba"))

    def test_tamano_legible_se_formatea_en_la_unidad_correcta(self):
        doc = Documento.objects.create(titulo="Contrato", archivo=_archivo_prueba())
        self.assertTrue(doc.tamano_legible.endswith("B"))

    def test_extension_se_extrae_del_nombre_del_archivo(self):
        doc = Documento.objects.create(titulo="Plano", archivo=_archivo_prueba("plano.dwg"))
        self.assertEqual(doc.extension, "DWG")

    def test_borrar_documento_borra_tambien_el_archivo_del_almacenamiento(self):
        doc = Documento.objects.create(titulo="Factura", archivo=_archivo_prueba("factura.pdf"))
        ruta = doc.archivo.path
        import os
        self.assertTrue(os.path.exists(ruta))
        doc.delete()
        self.assertFalse(os.path.exists(ruta))

    def test_extension_no_permitida_es_invalida(self):
        doc = Documento(titulo="Ejecutable", archivo=_archivo_prueba("virus.exe", b"x"))
        with self.assertRaises(ValidationError):
            doc.full_clean()


@override_settings(MEDIA_ROOT=MEDIA_ROOT_TEMPORAL)
class DocumentoVistasTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT_TEMPORAL, ignore_errors=True)

    def setUp(self):
        self.empresa = Empresa.objects.get(pk=1)
        self.usuario = User.objects.create_superuser(username="admin_docs", password="ClaveSegura123")
        PerfilUsuario.objects.create(usuario=self.usuario, empresa=self.empresa)
        self.client.force_login(self.usuario)

    def test_subir_documento_via_formulario(self):
        response = self.client.post(reverse("documentos:documento_subir"), {
            "titulo": "Contrato firmado", "categoria": Documento.CONTRATO, "archivo": _archivo_prueba(),
        })
        documento = Documento.objects.get(titulo="Contrato firmado")
        self.assertRedirects(response, reverse("documentos:documento_lista"))
        self.assertEqual(documento.empresa, self.empresa)
        self.assertEqual(documento.subido_por, self.usuario)

    def test_subir_documento_vinculado_a_proyecto_redirige_al_proyecto(self):
        proyecto = Proyecto.objects.create(empresa=self.empresa, nombre="Obra Test")
        response = self.client.post(reverse("documentos:documento_subir"), {
            "titulo": "Plano estructural", "categoria": Documento.PLANO,
            "archivo": _archivo_prueba("plano.pdf"), "proyecto": proyecto.pk,
        })
        self.assertRedirects(response, reverse("proyectos:proyecto_detalle", args=[proyecto.pk]))
        self.assertEqual(proyecto.documentos.count(), 1)

    def test_lista_muestra_solo_documentos_de_la_propia_empresa(self):
        otra_empresa = Empresa.objects.create(nombre="Otra constructora")
        Documento.objects.create(empresa=self.empresa, titulo="Documento propio", archivo=_archivo_prueba())
        Documento.objects.create(empresa=otra_empresa, titulo="Documento ajeno", archivo=_archivo_prueba())

        response = self.client.get(reverse("documentos:documento_lista"))
        titulos = [d.titulo for d in response.context["documentos"]]
        self.assertIn("Documento propio", titulos)
        self.assertNotIn("Documento ajeno", titulos)

    def test_eliminar_documento_lo_borra_de_la_base_y_del_almacenamiento(self):
        doc = Documento.objects.create(empresa=self.empresa, titulo="A borrar", archivo=_archivo_prueba())
        response = self.client.post(reverse("documentos:documento_eliminar", args=[doc.pk]))
        self.assertRedirects(response, reverse("documentos:documento_lista"))
        self.assertFalse(Documento.objects.filter(pk=doc.pk).exists())

    def test_no_puede_eliminar_documento_de_otra_empresa(self):
        otra_empresa = Empresa.objects.create(nombre="Otra constructora")
        doc_ajeno = Documento.objects.create(empresa=otra_empresa, titulo="Ajeno", archivo=_archivo_prueba())
        response = self.client.post(reverse("documentos:documento_eliminar", args=[doc_ajeno.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Documento.objects.filter(pk=doc_ajeno.pk).exists())

    def test_usuario_sin_permiso_de_modulo_no_puede_entrar(self):
        self.client.logout()
        limitado = User.objects.create_user(username="operario_sin_acceso_docs", password="ClaveSegura123")
        PerfilUsuario.objects.create(usuario=limitado, empresa=self.empresa)
        self.client.force_login(limitado)

        response = self.client.get(reverse("documentos:documento_lista"))
        self.assertRedirects(response, reverse("dashboard"))
