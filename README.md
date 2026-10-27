# TechStore U4 · Núcleo de negocio

**Actividad Práctica 4 · Componentes de Lógica de Negocio · Unidad 4 · FIME–UANL**

## Datos académicos

| Dato | Información |
|---|---|
| **Materia** | Componentes de lógica de negocios |
| **Actividad** | Actividad Práctica 4: Implementación del núcleo de negocio TechStore |
| **Profesor** | Miguel Ángel Gómez Marroquín |
| **Equipo** | 16 |
| **Grupo** | **004** |

### Integrantes

| Alumno(a) | Matrícula |
|---|---:|
| Lesly Adamaris Cotlame Nieto | 2226958 |
| Christopher Bethancourt Contreras | 2226948 |
| Francisco Mora Ruiz | 2226912 |

Este proyecto implementa en Python el núcleo de negocio de TechStore, una tienda ficticia de productos tecnológicos. Incluye entidades y Value Objects, reglas de descuentos con Specification Pattern, control de estados de pedidos, Domain Events, una API REST con FastAPI y pruebas automatizadas.

Los archivos CSV de `datos/` provienen del paquete original del profesor y se conservan sin modificaciones. `README.txt` también se mantiene como parte del material original.

## Estado de validación

Resultados de las últimas ejecuciones realizadas en el entorno virtual del proyecto:

- **Pruebas automatizadas:** `232 passed`. Se muestra una advertencia `DeprecationWarning` de una dependencia; no representa una prueba fallida.
- **Escenarios del profesor:** `15/15 escenarios cumplen su objetivo` (E01–E15).
- **Carga de datos:** 16 pedidos cargados. O001 aparece en estado `DRAFT`, con 4 unidades y un total de `2100.00` MXN.
- **API:** Uvicorn inició correctamente en el puerto `8000`; `/docs` y `/openapi.json` respondieron con HTTP 200.

Los resultados anteriores describen la ejecución verificada del proyecto en el entorno de trabajo; pueden variar si se modifica el código o las dependencias.

## Requisitos

- Python 3.11 o superior (el proyecto se probó con Python 3.13).
- Paquetes definidos en `requirements.txt`.
- Conexión a Internet para instalar las dependencias. Swagger UI puede requerir Internet para cargar sus recursos visuales.

## Instalación en Windows PowerShell

Abre PowerShell en la carpeta raíz `TechStore_U4` y ejecuta estos comandos, uno por uno:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

No es obligatorio activar el entorno virtual si ejecutas los comandos mediante `\.venv\Scripts\python.exe`, como en los ejemplos de este README. Si prefieres activarlo, utiliza:

```powershell
.\.venv\Scripts\Activate.ps1
```

Si PowerShell bloquea la activación, puedes omitirla y seguir usando el ejecutable de Python del entorno virtual indicado arriba.

## Comandos de verificación

Ejecuta los siguientes comandos desde la carpeta raíz del proyecto.

| Comando | Función | Resultado esperado |
|---|---|---|
| `\.venv\Scripts\python.exe cargar_csv.py` | Carga los CSV y muestra los pedidos con estado, unidades y total. | 16 pedidos; O001 muestra `DRAFT 4 2100.00`. |
| `\.venv\Scripts\python.exe -m pytest -q` | Ejecuta las pruebas automáticas de `tests/`. | En la última ejecución: `232 passed`. Puede aparecer una advertencia de una dependencia. |
| `\.venv\Scripts\python.exe ejecutar_escenarios.py --bitacora` | Ejecuta E01–E15 en modo detallado. | `15/15 escenarios cumplen su objetivo.` |
| `\.venv\Scripts\python.exe ejecutar_escenarios.py` | Ejecuta E01–E15 en modo normal. | `15/15 escenarios cumplen su objetivo.` |


## Iniciar la API REST

Desde PowerShell, en la carpeta raíz del proyecto, ejecuta el siguiente comando con el entorno virtual del proyecto:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api:app --host 127.0.0.1 --port 8000
```

Mientras la terminal esté abierta, visita:

- Swagger UI: <http://127.0.0.1:8000/docs>
- Esquema OpenAPI: <http://127.0.0.1:8000/openapi.json>

Para detener el servidor, regresa a PowerShell y presiona `Ctrl+C`.

La API carga los pedidos en memoria. Los cambios realizados desde la API se pierden cuando se reinicia el servidor; la actividad no requiere una base de datos.

## Reglas de negocio

### Descuentos

Las reglas están definidas en `app/specifications.py`.

| Descuento | Condiciones |
|---|---|
| 10 % (`VIP_DISCOUNT_SPEC`) | El cliente es VIP, el total es estrictamente mayor que 500 MXN, el pedido suma al menos 4 unidades y no tiene una promoción activa. |
| 5 % (`HIGH_AMOUNT_DISCOUNT_SPEC`) | El total es estrictamente mayor que 5,000 MXN y no hay una promoción activa. |
| 0 % | No se cumple ninguna de las reglas anteriores. |

Si se cumplen ambas reglas, prevalece el descuento del 10 %. Evaluar el descuento no modifica el pedido: `order.total` conserva el importe original, antes del descuento.

### Datos y límite de unidades

- `Money` representa importes con `Decimal`, valida los valores y evita los importes negativos o no finitos.
- `Customer` requiere un identificador no vacío y valores booleanos para `is_vip` y `active`. La identidad del cliente depende de su `id`.
- `OrderItem` valida sus datos y calcula el subtotal con base en la cantidad y el precio unitario.
- Cada pedido admite como máximo 20 unidades en total. Se suman las cantidades de los artículos; no se cuenta el número de renglones. Si se supera el límite, se produce `OrderItemLimitExceeded` sin modificar la lista de artículos.
- Solo se pueden agregar artículos mientras el pedido esté en `DRAFT`.
- El campo `existencia` de los CSV es información del catálogo. Esta práctica no exige descontar inventario.

## Estados y transiciones

Todos los pedidos comienzan en `DRAFT`. Las transiciones permitidas son:

| Transición | Método | Precondiciones | Domain Event |
|---|---|---|---|
| `DRAFT` → `CONFIRMED` | `confirm()` | El pedido tiene artículos y el cliente está activo. | `OrderConfirmed` |
| `CONFIRMED` → `SHIPPED` | `ship(tracking_number)` | La guía no está vacía. | `OrderShipped` |
| `CONFIRMED` → `CANCELLED` | `cancel(reason)` | El motivo no está vacío. | `OrderCancelled` |
| `SHIPPED` → `DELIVERED` | `deliver()` | No requiere datos adicionales. | `OrderDelivered` |
| `SHIPPED` → `RETURNED` | `return_order()` | No requiere datos adicionales. | `OrderReturned` |

`DELIVERED`, `RETURNED` y `CANCELLED` son estados finales. Las operaciones validan sus precondiciones antes de cambiar el estado y solo registran un evento después de una transición exitosa. Una operación inválida no cambia el estado ni registra un evento que no ocurrió.

- `InvalidOrderTransition`: la operación no está permitida desde el estado actual.
- `InvalidOrderData`: falta un dato requerido o no se cumple una precondición de datos.
- `OrderItemLimitExceeded`: la suma de unidades excedería el máximo permitido.

El diagrama de estados está disponible en `docs/diagramas/` en formato editable `.drawio`, además de `.png` y `.pdf`. Los documentos de apoyo —reporte, bitácora, explicación de Domain Events y reflexión— deben conservarse en formato editable `.docx` y también como `.pdf` dentro de sus respectivas carpetas de `docs/`.

## Domain Events

Los cinco eventos se guardan en `order.events`; la entidad expone la colección como solo lectura. No se publican a sistemas externos en esta actividad.

| Evento | Se registra cuando… |
|---|---|
| `OrderConfirmed` | `confirm()` cambia de `DRAFT` a `CONFIRMED`. |
| `OrderShipped` | `ship(tracking_number)` cambia de `CONFIRMED` a `SHIPPED`. |
| `OrderCancelled` | `cancel(reason)` cambia de `CONFIRMED` a `CANCELLED`. |
| `OrderDelivered` | `deliver()` cambia de `SHIPPED` a `DELIVERED`. |
| `OrderReturned` | `return_order()` cambia de `SHIPPED` a `RETURNED`. |

## API REST (`app/api.py`)

| Método | Endpoint | Cuerpo | Respuestas principales |
|---|---|---|---|
| GET | `/orders` | — | 200 |
| GET | `/orders/{order_id}` | — | 200, 404 |
| POST | `/orders/{order_id}/confirm` | — | 200, 404, 409, 422 |
| POST | `/orders/{order_id}/ship` | `{"tracking_number": "..."}` | 200, 404, 409, 422 |
| POST | `/orders/{order_id}/cancel` | `{"reason": "..."}` | 200, 404, 409, 422 |
| POST | `/orders/{order_id}/deliver` | — | 200, 404, 409 |
| POST | `/orders/{order_id}/return` | — | 200, 404, 409 |

| Código HTTP | Significado |
|---|---|
| 200 | Consulta u operación exitosa. |
| 404 | El pedido solicitado no existe (`OrderNotFound`). |
| 409 | La transición no está permitida desde el estado actual (`InvalidOrderTransition`). |
| 422 | Los datos, las precondiciones o el cuerpo de la solicitud no son válidos; también puede indicar que se excedió el límite de unidades. |

La respuesta de error utiliza un objeto JSON con información sobre la excepción y el mensaje. La respuesta exitosa incluye la información del pedido y del descuento calculado.

## Estructura del proyecto

```text
TechStore_U4/
├── app/
│   ├── __init__.py
│   ├── domain.py              # Entidades, Value Objects, estados, eventos y excepciones
│   ├── specifications.py     # Specifications y reglas de descuento
│   ├── service.py            # Casos de uso y acceso a pedidos
│   └── api.py                # API REST con FastAPI
├── datos/
│   ├── clientes.csv
│   ├── productos.csv
│   ├── pedidos.csv
│   ├── detalle_pedidos.csv
│   └── escenarios.csv
├── tests/
│   ├── conftest.py
│   ├── helpers.py
│   ├── test_domain.py
│   ├── test_specifications.py
│   ├── test_api.py
│   ├── test_escenarios.py
│   └── test_datos.py
├── docs/
│   ├── bitacora/
│   │   ├── Bitacora_Escenarios_TechStore.docx
│   │   └── Bitacora_Escenarios_TechStore.pdf
│   ├── diagramas/
│   │   ├── Diagrama_Estados_TechStore.drawio
│   │   ├── Diagrama_Estados_TechStore.png
│   │   └── Diagrama_Estados_TechStore.pdf
│   ├── domain events/
│   │   ├── Domain_Events_y_Diagrama_Estados_TechStore.docx
│   │   └── Domain_Events_y_Diagrama_Estados_TechStore.pdf
│   ├── reflexión/
│   │   ├── Reflexión_TechStore_U4.docx
│   │   └── Reflexión_TechStore_U4.pdf
│   └── reporte/
│       ├── Reporte_Actividad4_TechStore.docx
│       └── Reporte_Actividad4_TechStore.pdf
├── evidencias/
│   ├── 01_carga_16_pedidos.png
│   ├── 02_escenarios_E01_E15.png
│   ├── 03_pytest.png
│   ├── Evidencia_API_O001_200.png
│   ├── Evidencia_API_O001_409.png
│   ├── Evidencia_API_O007_422.png
│   └── Evidencia_API_O999_404.png
├── cargar_csv.py
├── ejecutar_escenarios.py
├── requirements.txt
├── pytest.ini
├── README.md                      # Este archivo
├── README.txt                     # Original del paquete del profesor
├── .gitattributes
└── .gitignore
```

El entorno virtual `.venv`, las carpetas `__pycache__`, los archivos `.pyc` y `.pytest_cache` son archivos locales de ejecución y no deben incluirse en el ZIP final ni subirse al repositorio.

## Evidencias de entrega

La carpeta `evidencias/` conserva capturas de la carga de datos, los escenarios, las pruebas automatizadas y las respuestas de la API. La captura `03_pytest.png` muestra las **232 pruebas aprobadas** de la última ejecución. Las capturas existentes de Swagger para 200, 404, 409 y 422 pueden conservarse si corresponden a las respuestas verificadas del proyecto.

La reflexión del equipo sobre los errores encontrados, sus soluciones y los aprendizajes está en `docs/reflexión/Reflexión_TechStore_U4.docx` y `docs/reflexión/Reflexión_TechStore_U4.pdf`.
