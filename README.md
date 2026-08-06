# ERP Gestión

Sistema de gestión empresarial (ERP) modular construido con Django. Módulos funcionales:
**Inventario**, **Ventas**, **Compras**, **Finanzas**, **Producción** y **RR.HH.**, integrados en
tiempo real — al confirmar una venta el stock se descuenta al instante y se genera su cuenta por
cobrar; al confirmar una compra (recepción de mercancía) el stock aumenta al instante y se genera
su cuenta por pagar; al completar una orden de producción se consumen las materias primas según la
receta y se da entrada al producto terminado; el control de asistencia y la nómina se gestionan
sobre los mismos empleados y departamentos. Todo queda registrado en el historial de movimientos de
inventario y en el estado financiero.

## Arquitectura

El proyecto está organizado en apps de Django, cada una representando un módulo independiente
que se puede extender o agregar sin afectar a los demás:

- **core**: dashboard, autenticación, comandos de datos semilla. Punto de entrada común.
- **inventario**: categorías, productos, stock y movimientos de inventario (entradas/salidas con trazabilidad).
- **ventas**: clientes, ventas (con líneas de detalle) y el flujo borrador → confirmada → anulada.
- **compras**: proveedores, compras (con líneas de detalle) y el mismo flujo borrador → confirmada → anulada.
- **finanzas**: cuentas por cobrar/pagar generadas automáticamente y registro de pagos (parciales o totales).
- **produccion**: listas de materiales (recetas) y órdenes de producción que consumen insumos y generan producto terminado.
- **rrhh**: empleados, departamentos, control de asistencia (entrada/salida) y nómina básica (bonificaciones/deducciones por período).
- **administracion**: datos de la empresa, gestión de usuarios (creación, edición, grupos de permisos, activar/desactivar, cambio de contraseña) y auditoría de actividad reciente. Solo define el modelo `Empresa` (vía `core`); para usuarios opera directamente sobre `auth.User`/`auth.Group`.

La integración entre inventario y transacciones ocurre en `ventas/models.py`
(`Venta.confirmar()` / `Venta.anular()`) y en `compras/models.py` (`Compra.confirmar()` /
`Compra.anular()`), que usan `inventario.models.registrar_movimiento()` dentro de una transacción
atómica con bloqueo de fila (`select_for_update`) para actualizar el stock de forma segura incluso
con varios usuarios concurrentes. Una venta descuenta stock (y anularla lo devuelve); una compra
confirmada lo aumenta (y anularla lo retira, validando que aún haya suficiente stock disponible).

La integración con finanzas es unidireccional y desacoplada: `finanzas/signals.py` escucha
`post_save` de `Venta` y `Compra` y genera la `CuentaPorCobrar`/`CuentaPorPagar` correspondiente
cuando pasan a **confirmada** (y las cancela si se anulan sin pagos registrados). Así, `ventas` y
`compras` no dependen de `finanzas` — se puede desinstalar el módulo financiero sin romper nada más.

`produccion/models.py` (`OrdenProduccion.completar()` / `OrdenProduccion.anular()`) sigue el mismo
patrón de `registrar_movimiento()` + `select_for_update()`: al crear una orden, el sistema calcula
automáticamente cuánto insumo se necesita según la `ListaMateriales` (receta) del producto y la
cantidad a producir, y guarda ese cálculo como snapshot (`ComponenteOrdenProduccion`) para no verse
afectado si la receta cambia después. Al completarla, descuenta cada insumo y da entrada al producto
terminado; al anularla, hace el proceso inverso (valida que aún haya suficiente producto terminado
en stock, por si ya se vendió).

El módulo `rrhh` no descuenta ni genera inventario, y tampoco depende de `finanzas` — sigue el mismo
principio de acoplamiento unidireccional: al **procesar** una nómina, `finanzas/signals.py` (que
también escucha `post_save` de `Nomina`) genera automáticamente una `CuentaPorPagar` por el total a
pagar. `CuentaPorPagar` admite dos orígenes mutuamente excluyentes — `compra` o `nomina` (reforzado
con un `CheckConstraint` en la base de datos) — y expone las propiedades `origen`/`contraparte` para
que las vistas y templates no necesiten distinguir el caso; así "Egresos" en el resumen financiero
suma compras confirmadas **y** nóminas procesadas, y desde la ficha de la nómina hay un enlace
directo a su cuenta por pagar en Finanzas (y viceversa).

## Módulo de administración

Disponible solo para usuarios con **acceso a Administración** (`is_staff`).

### Datos de la empresa

**Administración → Datos de la empresa**: nombre, NIT, dirección, teléfono, email, moneda y **logo**,
editables desde un único formulario. `core.models.Empresa` es un modelo **singleton** (siempre usa
`pk=1`; `Empresa.get_solo()` la obtiene o la crea con valores por defecto) y se expone a **todas**
las plantillas mediante el context processor `core.context_processors.empresa`, así que el nombre
de la empresa se refleja de inmediato en el shell bar, el `<title>` de la pestaña y la pantalla de
login — antes estos datos estaban fijos en el código.

El **logo** admite PNG, JPG o WEBP (máximo 2 MB); se guarda en `media/empresa/` y, una vez cargado,
reemplaza el ícono genérico en el shell bar, la pantalla de login y el encabezado de las
cotizaciones imprimibles. Al subir uno nuevo, el anterior se borra automáticamente del disco. En
desarrollo Django sirve `MEDIA_URL` directamente (`erp/urls.py`); en producción hace falta un
servidor de archivos/almacenamiento externo (ver sección de Seguridad).

### Auditoría

**Administración → Auditoría**: una línea de tiempo de solo lectura que combina, ordenados por
fecha descendente, los eventos más recientes de varias fuentes que ya existían en el sistema —
movimientos de inventario, pagos de clientes/proveedores y nóminas procesadas — cada uno con su
usuario, módulo y referencia. No es un log genérico con señales en cada modelo: reutiliza los campos
`usuario`/`registrado_por`/`procesada_por` que cada acción de negocio ya guardaba, así que no hay
modelos nuevos que mantener sincronizados. (Se añadió `Nomina.procesada_por` para completar el
registro, ya que antes no se guardaba quién procesaba la nómina.)

### Usuarios y permisos

**Administración → Usuarios**:

- Crear usuarios con contraseña, datos de contacto y asignación de **grupos de permisos**
  (Ventas, Inventario, Compras, Finanzas, Producción, RR.HH., Administración) mediante checkboxes.
- Editar usuarios existentes: datos, grupos, y los interruptores **Activo** / **Acceso a
  Administración**.
- **Activar/desactivar** una cuenta con un clic desde el listado.
- **Cambiar contraseña** de cualquier usuario sin necesitar la contraseña anterior.
- Un usuario no puede desactivarse a sí mismo ni quitarse su propio acceso de administración
  (evita bloqueos accidentales); ambas reglas se aplican tanto en el formulario de edición como en
  el botón rápido de activar/desactivar.

Las contraseñas se validan con los mismos `AUTH_PASSWORD_VALIDATORS` de Django ya configurados en
`erp/settings.py`. El panel `/admin/` de Django sigue disponible en paralelo para tareas más
avanzadas (permisos por objeto, grupos personalizados, etc.).

## Requisitos

- Python 3.9+ (probado con 3.9.6)

## Instalación

```bash
cd "Sistema de Gestion"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # ya viene un .env de desarrollo; en un clon nuevo, genera el tuyo (ver abajo)
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_data   # opcional: crea grupos de permisos y datos de ejemplo
python manage.py runserver
```

Abre http://127.0.0.1:8000 e inicia sesión con el superusuario creado.

`erp/settings.py` **exige** la variable `SECRET_KEY` (no hay valor por defecto en el código, ver
sección [Seguridad](#seguridad)); si `.env` no existe o no la define, `manage.py` falla con un
`KeyError` explícito en vez de arrancar con una clave insegura. Genera una propia con:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## Comando `seed_data`

Crea siete grupos de permisos (Administración, Ventas, Inventario, Compras, Finanzas, Producción,
RR.HH.) y, para cada tipo de dato que aún no exista, carga categorías, productos, clientes,
proveedores, una receta de ejemplo (Camiseta básica, hecha con 2 metros de tela por unidad) y dos
empleados de ejemplo. Es seguro ejecutarlo varias veces.

```bash
python manage.py seed_data
```

## Flujo de venta

1. **Ventas → Nueva venta**: se elige cliente, se agregan líneas de producto/cantidad (el precio
   se autocompleta desde el precio de venta del producto) y se guarda como **borrador**. El campo
   **IVA (%)** viene precargado con **19%** (tarifa general en Colombia) y se puede ajustar por
   venta si aplica otra tarifa (ej. 5%, 0% para productos exentos). El IVA se discrimina siempre
   por separado del subtotal, tanto en el formulario como en el detalle de la venta.
2. Un borrador se puede seguir editando libremente.
3. Al pulsar **Confirmar venta**, el sistema valida stock disponible línea por línea y lo descuenta
   de inmediato, dejando un `MovimientoInventario` de salida por cada línea con referencia al
   número de venta. La venta pasa a **confirmada** y ya no es editable.
4. Una venta confirmada se puede **anular**, lo que devuelve el stock al inventario (movimiento de
   entrada) y marca la venta como **anulada**.

## Cotizaciones

**Ventas → Cotizaciones → Nueva cotización**: mismo formulario de líneas producto/cantidad/precio
que una venta, pero **no afecta el inventario** — es solo un documento comercial.

1. Se crea en **borrador**, con un número autogenerado (`COT-000001`, ...) y una **fecha de
   validez** que por defecto son 15 días desde hoy (editable). Mientras está en borrador se puede
   seguir editando libremente.
2. **Marcar como enviada**: congela la cotización (ya no es editable) y registra la fecha de envío.
3. Desde "enviada" se puede **marcar como aceptada** o **rechazada**. Si pasa la fecha de validez
   sin resolverse, se muestra como **vencida**.
4. **Convertir en venta**: crea una venta nueva en **borrador** con las mismas líneas (no descuenta
   stock todavía — eso ocurre cuando esa venta se confirme, como cualquier otra). Una cotización solo
   se puede convertir una vez.
5. **Imprimir / PDF**: genera un documento independiente (sin el menú del ERP) con el logo y datos
   de la empresa, los datos del cliente, las líneas y los totales con IVA discriminado — listo para
   `Ctrl+P` → "Guardar como PDF" desde el navegador.

## Flujo de compra

1. **Compras → Nueva compra**: se elige proveedor, se agregan líneas de producto/cantidad (el precio
   se autocompleta desde el precio de costo del producto) y se guarda como **borrador**.
2. Un borrador se puede seguir editando libremente.
3. Al pulsar **Confirmar compra** (recepción de mercancía), el sistema aumenta el stock de inmediato,
   dejando un `MovimientoInventario` de entrada por cada línea con referencia al número de compra.
   La compra pasa a **confirmada** y ya no es editable.
4. Una compra confirmada se puede **anular**, lo que retira del inventario lo que había ingresado
   (validando que aún haya stock suficiente, por si ya se vendió) y marca la compra como **anulada**.

## Módulo de finanzas

- Al **confirmar una venta** se genera automáticamente una **cuenta por cobrar** (CxC) por el total
  de la venta; al **confirmar una compra** o **procesar una nómina**, una **cuenta por pagar** (CxP)
  por el total de la compra o de la nómina.
- Desde la ficha de cada cuenta (**Finanzas → Por cobrar / Por pagar**) se pueden **registrar pagos**
  parciales o totales (efectivo, transferencia, tarjeta, otro), con historial completo de pagos.
  El estado de la cuenta (pendiente/pago parcial/pagada) se actualiza automáticamente según el saldo.
- **Finanzas → Resumen**: KPIs de saldo total por cobrar, saldo total por pagar, ingresos (ventas
  confirmadas), egresos (compras confirmadas + nóminas procesadas) y balance neto, más los listados
  de cuentas pendientes.
- Si una venta o compra se anula **antes de recibir pagos**, su cuenta asociada se marca como
  **anulada** automáticamente; si ya tiene pagos registrados, se conserva para no perder el rastro
  contable.

## Módulo de producción

1. **Producción → Recetas (BOM)**: se define, para un producto terminado, qué insumos y en qué
   cantidad se necesitan para fabricar **1 unidad** (ej. "Camiseta básica" requiere 2 metros de tela).
2. **Producción → Nueva orden**: se elige el producto terminado (solo aparecen los que ya tienen
   receta) y la cantidad a producir; el sistema calcula automáticamente el total de cada insumo
   necesario y lo muestra junto al stock disponible, señalando en rojo si falta inventario.
3. Al pulsar **Completar producción**, se descuenta cada insumo de la receta y se da entrada al
   producto terminado, todo en una sola transacción. La orden pasa a **completada**.
4. Una orden completada se puede **anular**, lo que retira el producto terminado del inventario y
   devuelve los insumos consumidos (validando que aún haya suficiente producto terminado, por si ya
   se vendió).

## Módulo de RR.HH.

- **Empleados**: ficha con cargo, departamento, salario base, fecha de contratación y contacto.
- **Asistencia**: por cada día se puede **marcar entrada** (con un clic, hora automática) y luego
  **marcar salida**; también se puede registrar manualmente el estado (presente, tardanza, ausente,
  permiso, vacaciones) para días sin marcaje, por ejemplo una ausencia justificada.
- **Nómina**: se crea por período (ej. `2026-08`) y genera automáticamente un detalle por cada
  empleado activo con su salario base. Mientras esté en **borrador** se pueden ajustar bonificaciones
  y deducciones por empleado; al **procesar** la nómina, los montos quedan congelados, ya no son
  editables, y se genera automáticamente su cuenta por pagar en Finanzas.
- **RR.HH. → Resumen**: empleados activos, presentes/ausentes/sin registrar hoy, y la última nómina
  con su total y estado.

## Módulo de inventario

- Alertas automáticas de **stock bajo** (stock actual ≤ stock mínimo) visibles en el dashboard y en
  el listado de productos.
- Ajustes manuales de inventario (entradas/salidas) desde la ficha de cada producto, siempre con
  trazabilidad en el historial de movimientos.
- Valor de inventario calculado en tiempo real (stock × precio de costo).

## Pruebas

La lógica crítica del negocio (descuento/devolución de stock en ventas, aumento/retiro de stock en
compras, validación de stock insuficiente, cálculo de totales con impuesto, generación automática
de cuentas por cobrar/pagar y registro de pagos, consumo/reversión de insumos y producto terminado
en producción, marcaje de asistencia y cálculo/procesamiento de nómina, permisos y protección contra
auto-bloqueo en la gestión de usuarios, el singleton de datos de la empresa, el contenido de la
auditoría, el middleware de acceso por módulo y el bloqueo por fuerza bruta) está cubierta por
pruebas automatizadas:

```bash
python manage.py test
```

## Panel de administración

Disponible en `/admin/` para el superusuario: gestión avanzada de productos, categorías, clientes,
proveedores, ventas y compras (con líneas inline), recetas y órdenes de producción, empleados,
departamentos, asistencia y nóminas, consulta de movimientos de inventario y de cuentas por
cobrar/pagar con su historial de pagos (todo de solo lectura donde aplica, para preservar la
trazabilidad).

## Seguridad

### Secretos y configuración por entorno

`erp/settings.py` ya no trae `SECRET_KEY` escrita en el código. Al arrancar, lee un archivo `.env`
en la raíz del proyecto (no versionado — está en `.gitignore`) mediante un cargador de ~10 líneas
sin dependencias nuevas, y expone `SECRET_KEY`, `DEBUG` y `ALLOWED_HOSTS` desde ahí. Si `SECRET_KEY`
no está definida, Django **no arranca** (falla explícito en vez de usar una clave insegura por
defecto). `.env.example` documenta las variables sin exponer ningún secreto real.

### Cabeceras y cookies

- `SESSION_COOKIE_HTTPONLY`, `CSRF_COOKIE_HTTPONLY`, `X_FRAME_OPTIONS = 'DENY'` y
  `SECURE_CONTENT_TYPE_NOSNIFF` activos siempre.
- Sesión: expira a las 8 horas y también al cerrar el navegador (`SESSION_COOKIE_AGE`,
  `SESSION_EXPIRE_AT_BROWSER_CLOSE`).
- Cuando `DEBUG=False` (producción) se activan además `SECURE_SSL_REDIRECT`,
  `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` y HSTS — desactivados en desarrollo local a
  propósito, porque exigen HTTPS y romperían `runserver` por HTTP. Verificado corriendo
  `python manage.py check --deploy` con `DEBUG=True` (5 avisos, todos justificados por ser local)
  y con `DEBUG=False` (0 avisos).
- Política de contraseñas reforzada: `MinimumLengthValidator` subido a 10 caracteres, además de los
  validadores por defecto de Django (similitud con el usuario, contraseñas comunes, solo numéricas).

### Bloqueo por fuerza bruta (`django-axes`)

Tras **5 intentos fallidos** de login con el mismo usuario, la cuenta queda bloqueada 1 hora — un
intento posterior con la contraseña correcta también es rechazado hasta que pase el tiempo de
enfriamiento. Aplica tanto al login propio como al de `/admin/`, porque se engancha a nivel del
backend de autenticación (`AXES_FAILURE_LIMIT`, `AXES_COOLOFF_TIME` en `erp/settings.py`).

### Los grupos de permisos ahora sí se aplican

Antes, los grupos creados por `seed_data` (Ventas, Compras, Inventario, Finanzas, Producción,
RR.HH., Administración) existían pero **nada los consultaba** — cualquier usuario autenticado podía
entrar a cualquier módulo por URL. `core/middleware.py` (`ModuloAccesoMiddleware`) cierra ese hueco:
antes de servir una vista de `ventas`, `compras`, `inventario`, `finanzas`, `produccion` o `rrhh`,
verifica `request.user.has_module_perms(app_label)` — el mecanismo nativo de Django que ya respeta
superusuarios y permisos heredados de grupo — y si no lo tiene, redirige al dashboard con un
mensaje de error. Es un único middleware centralizado, no decoradores repetidos en ~80 vistas; los
namespaces `administracion` y `admin` ya tenían su propia protección (`staff_member_required`) y no
se tocaron.

### Notas de configuración adicionales

- La base de datos por defecto en desarrollo es SQLite (`db.sqlite3`). En producción, si la
  variable de entorno `DATABASE_URL` está definida, `erp/settings.py` la usa automáticamente en
  su lugar (pensado para PostgreSQL — ver sección "Despliegue en Render" abajo).
- Ajusta `TIME_ZONE` en `erp/settings.py` según tu ubicación.
- Antes de desplegar a producción: define un `.env` real con una `SECRET_KEY` propia, `DEBUG=False`
  y `ALLOWED_HOSTS` con tu dominio, y sirve la aplicación detrás de HTTPS (las cookies seguras y el
  redirect a SSL lo asumen).

## Despliegue en Render

El proyecto ya está preparado para desplegarse (PostgreSQL, archivos estáticos vía `whitenoise`,
servidor `gunicorn`, `render.yaml` con la infraestructura definida como código). Pasos que **debes
hacer tú** desde tu cuenta (no se pueden automatizar — requieren tu login/pago):

1. **Sube el código a GitHub** (o GitLab) si aún no lo has hecho — Render despliega desde un repo Git.
2. Crea una cuenta en [render.com](https://render.com) (tiene capa gratuita).
3. En el dashboard de Render: **New → Blueprint**, conecta el repositorio. Render detecta
   `render.yaml` automáticamente y propone crear:
   - Un **Web Service** (`erp-gestion`) con `gunicorn`, que instala dependencias, corre
     `collectstatic` y `migrate` en cada deploy.
   - Una base de datos **PostgreSQL** (`erp-db`) gratuita, ya enlazada al web service vía
     `DATABASE_URL`.
   - Una `SECRET_KEY` generada automáticamente por Render (segura, nunca la ves ni la gestionas).
4. Click en **Apply** — Render construye y despliega. La primera vez tarda unos minutos.
5. Cuando termine, entra a la URL que te da Render (`https://erp-gestion-xxxx.onrender.com`) y crea
   tu superusuario desde la consola/Shell de Render (pestaña "Shell" del servicio):
   ```bash
   python manage.py createsuperuser
   python manage.py seed_data
   ```
6. Inicia sesión y ve a **Administración → Datos de la empresa** para subir el logo y completar los
   datos — igual que en local.

**Limitación a tener en cuenta:** el disco del plan gratuito de Render es efímero — cualquier
archivo subido (como el logo de la empresa) se borra en cada redeploy o reinicio del servicio. Para
que los archivos subidos persistan, más adelante se puede agregar un disco persistente de Render
(plan pago) o un almacenamiento externo tipo Cloudinary/S3; no está configurado todavía porque no
hacía falta para empezar a usar el sistema.

**Costos:** el plan gratuito de Render "duerme" el servicio tras un rato sin tráfico (la primera
carga después de eso tarda ~30 segundos en despertar) y tiene límites de horas/mes. Si varios
empleados lo usan todo el día de forma continua, conviene pasar al plan pago más económico para
evitar esas pausas.
