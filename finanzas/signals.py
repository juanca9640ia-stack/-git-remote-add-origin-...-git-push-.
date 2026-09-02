from decimal import Decimal

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from compras.models import Compra
from rrhh.models import Nomina
from ventas.models import Venta

from .models import CuentaPorCobrar, CuentaPorPagar

DIAS_PLAZO_CXC = 30


@receiver(post_save, sender=Venta)
def sincronizar_cuenta_por_cobrar(sender, instance, **kwargs):
    """Al confirmar una venta se genera su cuenta por cobrar; al anularla (sin pagos) se cancela."""
    if instance.estado == Venta.CONFIRMADA:
        vencimiento = timezone.localdate() + timezone.timedelta(days=DIAS_PLAZO_CXC)
        CuentaPorCobrar.objects.get_or_create(
            venta=instance,
            defaults={
                "empresa": instance.empresa,
                "monto_total": instance.total, "saldo_pendiente": instance.total,
                "fecha_vencimiento": vencimiento,
            },
        )
    elif instance.estado == Venta.ANULADA:
        cuenta = CuentaPorCobrar.objects.filter(venta=instance).exclude(estado=CuentaPorCobrar.ANULADA).first()
        if cuenta and cuenta.saldo_pendiente == cuenta.monto_total:
            cuenta.estado = CuentaPorCobrar.ANULADA
            cuenta.saldo_pendiente = Decimal("0")
            cuenta.save(update_fields=["estado", "saldo_pendiente"])


@receiver(post_save, sender=Compra)
def sincronizar_cuenta_por_pagar(sender, instance, **kwargs):
    """Al confirmar una compra se genera su cuenta por pagar; al anularla (sin pagos) se cancela."""
    if instance.estado == Compra.CONFIRMADA:
        CuentaPorPagar.objects.get_or_create(
            compra=instance,
            defaults={
                "empresa": instance.empresa,
                "monto_total": instance.total, "saldo_pendiente": instance.total,
            },
        )
    elif instance.estado == Compra.ANULADA:
        cuenta = CuentaPorPagar.objects.filter(compra=instance).exclude(estado=CuentaPorPagar.ANULADA).first()
        if cuenta and cuenta.saldo_pendiente == cuenta.monto_total:
            cuenta.estado = CuentaPorPagar.ANULADA
            cuenta.saldo_pendiente = Decimal("0")
            cuenta.save(update_fields=["estado", "saldo_pendiente"])


@receiver(post_save, sender=Nomina)
def sincronizar_cuenta_por_pagar_nomina(sender, instance, **kwargs):
    """Al procesar una nómina se genera la cuenta por pagar correspondiente a su total."""
    if instance.estado == Nomina.PROCESADA:
        CuentaPorPagar.objects.get_or_create(
            nomina=instance,
            defaults={
                "empresa": instance.empresa,
                "monto_total": instance.total_pagar, "saldo_pendiente": instance.total_pagar,
            },
        )
