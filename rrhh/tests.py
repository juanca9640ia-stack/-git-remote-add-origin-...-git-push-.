import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from rrhh.forms import DetalleNominaForm, EmpleadoForm, NominaForm
from rrhh.models import AbonoPrestamo, Asistencia, Departamento, DetalleNomina, Empleado, Nomina, Prestamo, rango_periodo


class AsistenciaTests(TestCase):
    def setUp(self):
        self.departamento = Departamento.objects.create(nombre="Ventas")
        self.empleado = Empleado.objects.create(
            nombre_completo="Laura Gómez", documento="1001", cargo="Vendedora",
            departamento=self.departamento, salario_base=Decimal("1500000"),
        )

    def test_marcar_salida_sin_entrada_falla(self):
        asistencia = Asistencia.objects.create(empleado=self.empleado, fecha=timezone.localdate())
        with self.assertRaises(ValidationError):
            asistencia.marcar_salida()

    def test_marcar_salida_registra_hora(self):
        asistencia = Asistencia.objects.create(
            empleado=self.empleado, fecha=timezone.localdate(),
            hora_entrada=timezone.localtime().time(),
        )
        asistencia.marcar_salida()
        asistencia.refresh_from_db()
        self.assertIsNotNone(asistencia.hora_salida)

    def test_no_permite_marcar_salida_dos_veces(self):
        asistencia = Asistencia.objects.create(
            empleado=self.empleado, fecha=timezone.localdate(),
            hora_entrada=timezone.localtime().time(),
        )
        asistencia.marcar_salida()
        with self.assertRaises(ValidationError):
            asistencia.marcar_salida()

    def test_un_solo_registro_de_asistencia_por_dia(self):
        Asistencia.objects.create(empleado=self.empleado, fecha=timezone.localdate())
        with self.assertRaises(Exception):
            Asistencia.objects.create(empleado=self.empleado, fecha=timezone.localdate())


class NominaTests(TestCase):
    def setUp(self):
        self.departamento = Departamento.objects.create(nombre="Ventas")
        self.empleado_activo = Empleado.objects.create(
            nombre_completo="Laura Gómez", documento="1001", cargo="Vendedora",
            departamento=self.departamento, salario_base=Decimal("1500000"), activo=True,
        )
        self.empleado_inactivo = Empleado.objects.create(
            nombre_completo="Ex Empleado", documento="1002", cargo="Vendedor",
            departamento=self.departamento, salario_base=Decimal("1200000"), activo=False,
        )

    def test_generar_detalles_solo_incluye_empleados_activos(self):
        nomina = Nomina.objects.create(periodo="2026-08")
        nomina.generar_detalles()

        self.assertEqual(nomina.detalles.count(), 1)
        detalle = nomina.detalles.first()
        self.assertEqual(detalle.empleado, self.empleado_activo)
        self.assertEqual(detalle.salario_base, Decimal("1500000"))

    def test_total_detalle_incluye_bonificaciones_y_deducciones(self):
        nomina = Nomina.objects.create(periodo="2026-08")
        nomina.generar_detalles()
        detalle = nomina.detalles.first()
        detalle.bonificaciones = Decimal("100000")
        detalle.deducciones = Decimal("50000")
        detalle.save()

        self.assertEqual(detalle.total, Decimal("1550000"))
        self.assertEqual(nomina.total_pagar, Decimal("1550000"))

    def test_total_detalle_incluye_horas_extra_y_descuento_prestamo(self):
        nomina = Nomina.objects.create(periodo="2026-08")
        nomina.generar_detalles()
        detalle = nomina.detalles.first()
        detalle.horas_extra = Decimal("80000")
        detalle.descuento_prestamo = Decimal("30000")
        detalle.save()

        self.assertEqual(detalle.total, Decimal("1550000"))

    def test_no_permite_procesar_nomina_sin_detalles(self):
        nomina = Nomina.objects.create(periodo="2026-08")
        with self.assertRaises(ValidationError):
            nomina.procesar()

    def test_procesar_nomina_cambia_estado(self):
        nomina = Nomina.objects.create(periodo="2026-08")
        nomina.generar_detalles()
        nomina.procesar()

        nomina.refresh_from_db()
        self.assertEqual(nomina.estado, Nomina.PROCESADA)
        self.assertIsNotNone(nomina.procesada_en)

    def test_no_permite_procesar_nomina_ya_procesada(self):
        nomina = Nomina.objects.create(periodo="2026-08")
        nomina.generar_detalles()
        nomina.procesar()

        with self.assertRaises(ValidationError):
            nomina.procesar()

    def test_no_permite_regenerar_detalles_de_nomina_procesada(self):
        nomina = Nomina.objects.create(periodo="2026-08")
        nomina.generar_detalles()
        nomina.procesar()

        with self.assertRaises(ValidationError):
            nomina.generar_detalles()


class PrestamoTests(TestCase):
    def setUp(self):
        self.empleado = Empleado.objects.create(
            nombre_completo="Laura Gómez", documento="1001", cargo="Vendedora",
            salario_base=Decimal("1500000"), activo=True,
        )

    def test_saldo_pendiente_se_inicializa_con_el_monto(self):
        prestamo = Prestamo.objects.create(empleado=self.empleado, monto=Decimal("300000"))
        self.assertEqual(prestamo.saldo_pendiente, Decimal("300000"))
        self.assertEqual(prestamo.estado, Prestamo.ACTIVO)

    def test_abonar_reduce_saldo_y_registra_movimiento(self):
        prestamo = Prestamo.objects.create(empleado=self.empleado, monto=Decimal("300000"))
        abonado = prestamo.abonar(Decimal("100000"))

        self.assertEqual(abonado, Decimal("100000"))
        prestamo.refresh_from_db()
        self.assertEqual(prestamo.saldo_pendiente, Decimal("200000"))
        self.assertEqual(prestamo.estado, Prestamo.ACTIVO)
        self.assertEqual(AbonoPrestamo.objects.filter(prestamo=prestamo).count(), 1)

    def test_abonar_no_excede_el_saldo_pendiente(self):
        prestamo = Prestamo.objects.create(empleado=self.empleado, monto=Decimal("100000"))
        abonado = prestamo.abonar(Decimal("999999"))

        self.assertEqual(abonado, Decimal("100000"))
        prestamo.refresh_from_db()
        self.assertEqual(prestamo.saldo_pendiente, Decimal("0"))
        self.assertEqual(prestamo.estado, Prestamo.PAGADO)

    def test_procesar_nomina_aplica_descuento_al_prestamo_activo(self):
        prestamo = Prestamo.objects.create(empleado=self.empleado, monto=Decimal("300000"))
        nomina = Nomina.objects.create(periodo="2026-08")
        nomina.generar_detalles()
        detalle = nomina.detalles.first()
        detalle.descuento_prestamo = Decimal("100000")
        detalle.save()

        nomina.procesar()

        prestamo.refresh_from_db()
        self.assertEqual(prestamo.saldo_pendiente, Decimal("200000"))
        abono = AbonoPrestamo.objects.get(prestamo=prestamo)
        self.assertEqual(abono.valor, Decimal("100000"))
        self.assertEqual(abono.nomina, nomina)

    def test_procesar_nomina_aplica_descuento_fifo_entre_varios_prestamos(self):
        prestamo_antiguo = Prestamo.objects.create(
            empleado=self.empleado, monto=Decimal("50000"), fecha_otorgado=timezone.localdate() - timezone.timedelta(days=10),
        )
        prestamo_reciente = Prestamo.objects.create(
            empleado=self.empleado, monto=Decimal("200000"), fecha_otorgado=timezone.localdate(),
        )
        nomina = Nomina.objects.create(periodo="2026-08")
        nomina.generar_detalles()
        detalle = nomina.detalles.first()
        detalle.descuento_prestamo = Decimal("80000")
        detalle.save()

        nomina.procesar()

        prestamo_antiguo.refresh_from_db()
        prestamo_reciente.refresh_from_db()
        self.assertEqual(prestamo_antiguo.saldo_pendiente, Decimal("0"))
        self.assertEqual(prestamo_antiguo.estado, Prestamo.PAGADO)
        self.assertEqual(prestamo_reciente.saldo_pendiente, Decimal("170000"))

    def test_form_rechaza_descuento_mayor_al_saldo_disponible(self):
        Prestamo.objects.create(empleado=self.empleado, monto=Decimal("50000"))
        nomina = Nomina.objects.create(periodo="2026-08")
        nomina.generar_detalles()
        detalle = nomina.detalles.first()

        form = DetalleNominaForm(
            data={
                "horas_extra": "0", "bonificaciones": "0",
                "deducciones": "0", "descuento_prestamo": "100000",
            },
            instance=detalle,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("descuento_prestamo", form.errors)


class PagoPorDiaTests(TestCase):
    def setUp(self):
        self.empleado_salario = Empleado.objects.create(
            nombre_completo="Laura Gómez", documento="1001", cargo="Vendedora",
            telefono="3000000000", salario_base=Decimal("1500000"), activo=True,
        )
        self.empleado_dia = Empleado.objects.create(
            nombre_completo="Pedro Ruiz", documento="1003", cargo="Operario",
            telefono="3000000001", tipo_pago=Empleado.PAGO_DIA, valor_dia=Decimal("60000"), activo=True,
        )

    def test_generar_detalles_toma_salario_o_valor_dia_segun_tipo(self):
        nomina = Nomina.objects.create(periodo="2026-08")
        nomina.generar_detalles()

        detalle_salario = nomina.detalles.get(empleado=self.empleado_salario)
        self.assertEqual(detalle_salario.salario_base, Decimal("1500000"))
        self.assertEqual(detalle_salario.valor_dia, Decimal("0"))

        detalle_dia = nomina.detalles.get(empleado=self.empleado_dia)
        self.assertEqual(detalle_dia.salario_base, Decimal("0"))
        self.assertEqual(detalle_dia.valor_dia, Decimal("60000"))

    def test_dias_trabajados_se_cuentan_de_asistencia_con_entrada(self):
        for dia in (1, 2, 3):
            Asistencia.objects.create(
                empleado=self.empleado_dia, fecha=f"2026-08-0{dia}", hora_entrada="08:00",
            )
        Asistencia.objects.create(empleado=self.empleado_dia, fecha="2026-08-04", estado=Asistencia.AUSENTE)

        nomina = Nomina.objects.create(periodo="2026-08")
        nomina.generar_detalles()

        detalle = nomina.detalles.get(empleado=self.empleado_dia)
        self.assertEqual(detalle.dias_trabajados, 3)
        self.assertEqual(detalle.pago_base, Decimal("180000"))

    def test_dias_trabajados_solo_cuenta_periodo_de_la_nomina(self):
        Asistencia.objects.create(empleado=self.empleado_dia, fecha="2026-07-30", hora_entrada="08:00")
        Asistencia.objects.create(empleado=self.empleado_dia, fecha="2026-08-01", hora_entrada="08:00")

        nomina = Nomina.objects.create(periodo="2026-08")
        nomina.generar_detalles()

        detalle = nomina.detalles.get(empleado=self.empleado_dia)
        self.assertEqual(detalle.dias_trabajados, 1)

    def test_recalcular_dias_trabajados_refleja_asistencia_nueva(self):
        nomina = Nomina.objects.create(periodo="2026-08")
        nomina.generar_detalles()
        detalle = nomina.detalles.get(empleado=self.empleado_dia)
        self.assertEqual(detalle.dias_trabajados, 0)

        Asistencia.objects.create(empleado=self.empleado_dia, fecha="2026-08-05", hora_entrada="08:00")
        detalle.recalcular_dias_trabajados()

        self.assertEqual(detalle.dias_trabajados, 1)

    def test_recalcular_dias_trabajados_no_afecta_empleado_por_salario(self):
        Asistencia.objects.create(empleado=self.empleado_salario, fecha="2026-08-01", hora_entrada="08:00")
        nomina = Nomina.objects.create(periodo="2026-08")
        nomina.generar_detalles()

        detalle = nomina.detalles.get(empleado=self.empleado_salario)
        self.assertEqual(detalle.dias_trabajados, 0)
        self.assertEqual(detalle.pago_base, Decimal("1500000"))

    def test_dias_trabajados_no_es_editable_en_el_formulario(self):
        self.assertNotIn("dias_trabajados", DetalleNominaForm.base_fields)

    def test_pago_base_por_dia_multiplica_dias_por_valor(self):
        nomina = Nomina.objects.create(periodo="2026-08")
        nomina.generar_detalles()
        detalle = nomina.detalles.get(empleado=self.empleado_dia)
        detalle.dias_trabajados = 12
        detalle.save()

        self.assertEqual(detalle.pago_base, Decimal("720000"))
        self.assertEqual(detalle.total, Decimal("720000"))

    def test_pago_base_por_salario_ignora_dias_trabajados(self):
        nomina = Nomina.objects.create(periodo="2026-08")
        nomina.generar_detalles()
        detalle = nomina.detalles.get(empleado=self.empleado_salario)
        detalle.dias_trabajados = 20
        detalle.save()

        self.assertEqual(detalle.pago_base, Decimal("1500000"))


class EmpleadoFormTests(TestCase):
    def _datos_base(self, **overrides):
        datos = dict(
            nombre_completo="Ana Torres", documento="2001", cargo="Analista",
            email="", telefono="3001234567", fecha_contratacion="2026-08-05",
            tipo_pago=Empleado.PAGO_SALARIO, salario_base="2000000", valor_dia="0",
            activo=True,
        )
        datos.update(overrides)
        return datos

    def test_telefono_es_obligatorio(self):
        form = EmpleadoForm(data=self._datos_base(telefono=""))
        self.assertFalse(form.is_valid())
        self.assertIn("telefono", form.errors)

    def test_requiere_salario_base_si_tipo_pago_es_salario(self):
        form = EmpleadoForm(data=self._datos_base(salario_base="0"))
        self.assertFalse(form.is_valid())
        self.assertIn("salario_base", form.errors)

    def test_requiere_valor_dia_si_tipo_pago_es_dia(self):
        form = EmpleadoForm(data=self._datos_base(tipo_pago=Empleado.PAGO_DIA, valor_dia="0"))
        self.assertFalse(form.is_valid())
        self.assertIn("valor_dia", form.errors)

    def test_formulario_valido_con_datos_completos(self):
        form = EmpleadoForm(data=self._datos_base())
        self.assertTrue(form.is_valid(), form.errors)


class NominaPeriodoSemanalTests(TestCase):
    def setUp(self):
        self.empleado = Empleado.objects.create(
            nombre_completo="Pedro Ruiz", documento="1003", cargo="Operario",
            telefono="3000000001", tipo_pago=Empleado.PAGO_DIA, valor_dia=Decimal("60000"), activo=True,
        )

    def test_rango_periodo_mensual(self):
        inicio, fin = rango_periodo("2026-08")
        self.assertEqual(str(inicio), "2026-08-01")
        self.assertEqual(str(fin), "2026-08-31")

    def test_rango_periodo_semanal(self):
        inicio, fin = rango_periodo("2026-W32")
        self.assertEqual((fin - inicio).days, 6)
        self.assertEqual(inicio.isoweekday(), 1)
        self.assertEqual(fin.isoweekday(), 7)

    def test_rango_periodo_formato_invalido(self):
        with self.assertRaises(ValidationError):
            rango_periodo("2026/08")

    def test_form_acepta_periodo_semanal(self):
        form = NominaForm(data={"periodo": "2026-w32"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["periodo"], "2026-W32")

    def test_form_rechaza_semana_iso_invalida(self):
        form = NominaForm(data={"periodo": "2026-W60"})
        self.assertFalse(form.is_valid())

    def test_dias_trabajados_respeta_rango_semanal(self):
        inicio, _ = rango_periodo("2026-W32")
        Asistencia.objects.create(empleado=self.empleado, fecha=inicio, hora_entrada="08:00")
        Asistencia.objects.create(
            empleado=self.empleado, fecha=inicio - datetime.timedelta(days=1), hora_entrada="08:00",
        )

        nomina = Nomina.objects.create(periodo="2026-W32")
        nomina.generar_detalles()

        detalle = nomina.detalles.get(empleado=self.empleado)
        self.assertEqual(detalle.dias_trabajados, 1)

    def test_nomina_total_pagar_suma_todos_los_detalles(self):
        empleado_2 = Empleado.objects.create(
            nombre_completo="Ana Ruiz", documento="1004", cargo="Operaria",
            telefono="3000000002", tipo_pago=Empleado.PAGO_DIA, valor_dia=Decimal("50000"), activo=True,
        )
        inicio, _ = rango_periodo("2026-W32")
        for emp in (self.empleado, empleado_2):
            Asistencia.objects.create(empleado=emp, fecha=inicio, hora_entrada="08:00")

        nomina = Nomina.objects.create(periodo="2026-W32")
        nomina.generar_detalles()

        self.assertEqual(nomina.total_pagar, Decimal("110000"))
