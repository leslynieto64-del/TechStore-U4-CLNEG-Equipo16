"""Ejecuta los escenarios E01–E15 de datos/escenarios.csv contra el dominio real.

Uso (desde la carpeta del proyecto):

    python ejecutar_escenarios.py                 # muestra los resultados
    python ejecutar_escenarios.py --bitacora      # además escribe docs/bitacora_escenarios.md

Cada escenario usa una carga NUEVA de los CSV (load_fixture), así que un caso
que cambia el estado de un pedido no contamina a los siguientes. No se
modifica ningún CSV: el escenario solo lee el pedido y ejecuta operaciones.
"""
from __future__ import annotations

import platform
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.domain import DomainException, Money, Order, OrderItem
from app.specifications import (
    HIGH_AMOUNT_DISCOUNT_SPEC,
    VIP_DISCOUNT_SPEC,
    discount_amount,
    discount_rate,
    total_with_discount,
)
from cargar_csv import load_fixture, rows

BASE = Path(__file__).resolve().parent
BITACORA = BASE / "docs" / "bitacora_escenarios.md"
GUIA_PRUEBA = "MX-GUIA-0001"
MOTIVO_PRUEBA = "Solicitud del cliente"

# Pasos de cada acción del CSV: (nombre del paso, función que lo ejecuta).
PASOS = {
    "confirmar": ("confirmar", lambda o: o.confirm()),
    "enviar": ("enviar", lambda o: o.ship(GUIA_PRUEBA)),
    "enviar sin guia": ("enviar sin guía", lambda o: o.ship("")),
    "cancelar": ("cancelar", lambda o: o.cancel(MOTIVO_PRUEBA)),
    "devolver": ("devolver", lambda o: o.return_order()),
    "entregar": ("entregar", lambda o: o.deliver()),
}
ACCIONES = {
    "confirmar": ["confirmar"],
    "confirmar y enviar sin guia": ["confirmar", "enviar sin guia"],
    "confirmar dos veces": ["confirmar", "confirmar"],
    "confirmar, enviar y cancelar": ["confirmar", "enviar", "cancelar"],
    "confirmar, enviar y devolver": ["confirmar", "enviar", "devolver"],
    "confirmar, enviar y entregar": ["confirmar", "enviar", "entregar"],
}
# Sustantivo que usa la columna "objetivo" para el paso rechazado.
SUSTANTIVO_RECHAZO = {
    "enviar sin guia": "envio",
    "enviar": "envio",
    "cancelar": "cancelacion",
    "devolver": "devolucion",
    "entregar": "entrega",
}


@dataclass
class Paso:
    descripcion: str
    exito: bool
    detalle: str
    evento: str | None = None


@dataclass
class ResultadoEscenario:
    caso_id: str
    pedido_id: str
    accion: str
    objetivo: str
    pista: str
    estado_inicial: str
    unidades_inicial: int
    total_inicial: str
    resultado: str = ""
    estado_final: str = ""
    unidades_final: int = 0
    total_final: str = ""
    eventos: list[str] = field(default_factory=list)
    pasos: list[Paso] = field(default_factory=list)
    invariantes_ok: bool = True
    explicacion: str = ""

    @property
    def cumple(self) -> bool:
        return self.resultado == self.objetivo and self.invariantes_ok


def _snapshot(order: Order):
    return (order.status, order.items, order.events, order.total, order.units)


def _si_no(valor: bool) -> str:
    return "sí" if valor else "no"


def _desglose_descuento(order: Order) -> str:
    total = order.total.amount
    partes_10 = [
        f"VIP {_si_no(order.customer.is_vip)}",
        f"total {total} > 500 {_si_no(total > Decimal('500'))}",
        f"unidades {order.units} ≥ 4 {_si_no(order.units >= 4)}",
        f"sin promoción {_si_no(not order.has_promotion)}",
    ]
    partes_5 = [
        f"total {total} > 5000 {_si_no(total > Decimal('5000'))}",
        f"sin promoción {_si_no(not order.has_promotion)}",
    ]
    return (
        f"Regla 10 % (AND): {', '.join(partes_10)} → "
        f"{'cumple' if VIP_DISCOUNT_SPEC.is_satisfied_by(order) else 'no cumple'}. "
        f"Regla 5 % (AND): {', '.join(partes_5)} → "
        f"{'cumple' if HIGH_AMOUNT_DISCOUNT_SPEC.is_satisfied_by(order) else 'no cumple'}."
    )


def _evaluar_descuento(order: Order, r: ResultadoEscenario) -> None:
    antes = _snapshot(order)
    tasa = discount_rate(order)
    r.resultado = f"{int(tasa * 100)}%"
    r.invariantes_ok = _snapshot(order) == antes  # La Specification no modifica el pedido.
    r.pasos.append(
        Paso(
            "evaluar descuento",
            True,
            f"tasa {tasa}, descuento {discount_amount(order).amount} MXN, "
            f"total con descuento {total_with_discount(order).amount} MXN",
        )
    )
    r.explicacion = (
        f"{_desglose_descuento(order)} Resultado {r.resultado}. "
        f"Evaluar una Specification no cambia el pedido ni registra eventos "
        f"(eventos: {len(order.events)})."
    )


def _agregar(order: Order, r: ResultadoEscenario, sku: str, cantidad: int) -> None:
    precios = {x["sku"]: Decimal(x["precio_mxn"]) for x in rows("productos.csv")}
    item = OrderItem(sku, cantidad, Money(precios[sku]))
    antes = _snapshot(order)
    try:
        order.add_item(item)
    except DomainException as exc:
        r.resultado = "rechazo"
        r.invariantes_ok = _snapshot(order) == antes
        r.pasos.append(Paso(f"add_item({sku} × {cantidad})", False, f"{type(exc).__name__}: {exc}"))
        r.explicacion = (
            f"Límite de 20 unidades por pedido (se suman cantidades, no renglones): "
            f"{antes[4]} + {cantidad} = {antes[4] + cantidad} > 20. Se lanzó "
            f"{type(exc).__name__} antes de modificar items; el pedido conserva "
            f"{order.units} unidades. add_item no registra eventos."
        )
    else:
        r.resultado = "exito"
        r.pasos.append(Paso(f"add_item({sku} × {cantidad})", True, "artículo agregado"))
        r.explicacion = f"Se agregó el artículo; el pedido tiene {order.units} unidades."


def _transiciones(order: Order, r: ResultadoEscenario, pasos: list[str]) -> None:
    hechos: list[str] = []
    for clave in pasos:
        descripcion, operacion = PASOS[clave]
        antes = _snapshot(order)
        eventos_antes = len(order.events)
        try:
            operacion(order)
        except DomainException as exc:
            r.invariantes_ok = _snapshot(order) == antes
            r.pasos.append(Paso(descripcion, False, f"{type(exc).__name__}: {exc}"))
            if len(pasos) == 1:
                r.resultado = "rechazo"
            elif clave in hechos:
                r.resultado = "rechazo segunda"
            else:
                r.resultado = f"rechazo {SUSTANTIVO_RECHAZO.get(clave, clave)}"
            return
        evento = order.events[-1].name if len(order.events) > eventos_antes else None
        r.pasos.append(Paso(descripcion, True, f"→ {order.status.value}", evento))
        hechos.append(clave)
    r.resultado = "exito"


def _explicar_transiciones(order: Order, r: ResultadoEscenario) -> None:
    trozos = []
    for paso in r.pasos:
        if paso.exito:
            trozos.append(f"{paso.descripcion} ✔ {paso.detalle} (evento {paso.evento})")
        else:
            trozos.append(
                f"{paso.descripcion} ✘ {paso.detalle} — sin cambio de estado y sin evento nuevo"
            )
    r.explicacion = (
        f"Regla: {r.pista}. " + "; ".join(trozos) + f". Estado final {order.status.value}."
    )


def ejecutar_escenario(fila: dict[str, str]) -> ResultadoEscenario:
    orders = load_fixture()  # Carga nueva: aislamiento entre escenarios.
    order = orders[fila["pedido_id"]]
    r = ResultadoEscenario(
        caso_id=fila["caso_id"],
        pedido_id=fila["pedido_id"],
        accion=fila["accion"],
        objetivo=fila["objetivo"],
        pista=fila["pista"],
        estado_inicial=order.status.value,
        unidades_inicial=order.units,
        total_inicial=str(order.total.amount),
    )
    accion = fila["accion"].strip()
    agregar = re.fullmatch(r"agregar (\S+) x(\d+)", accion)
    if accion == "evaluar_descuento":
        _evaluar_descuento(order, r)
    elif agregar:
        _agregar(order, r, agregar.group(1), int(agregar.group(2)))
    elif accion in ACCIONES:
        _transiciones(order, r, ACCIONES[accion])
        _explicar_transiciones(order, r)
    else:
        raise ValueError(f"Acción no reconocida en escenarios.csv: {accion!r}")
    r.estado_final = order.status.value
    r.unidades_final = order.units
    r.total_final = str(order.total.amount)
    r.eventos = [e.name for e in order.events]
    return r


def ejecutar_todos() -> list[ResultadoEscenario]:
    return [ejecutar_escenario(fila) for fila in rows("escenarios.csv")]


def _operacion_legible(r: ResultadoEscenario) -> str:
    return " → ".join(p.descripcion for p in r.pasos)


def _resultado_legible(r: ResultadoEscenario) -> str:
    marca = "✅ cumple" if r.cumple else "❌ NO cumple"
    return f"{r.resultado} ({marca}); estado final {r.estado_final}"


def escribir_bitacora(resultados: list[ResultadoEscenario], destino: Path = BITACORA) -> None:
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    aprobados = sum(r.cumple for r in resultados)
    lineas = [
        "# Bitácora de escenarios E01–E15",
        "",
        "> Archivo **generado automáticamente** por `python ejecutar_escenarios.py --bitacora` "
        "a partir de una ejecución real sobre `datos/escenarios.csv` y los CSV originales.",
        f"> Última ejecución: {ahora} · Python {platform.python_version()} · "
        f"resultado: **{aprobados}/{len(resultados)} escenarios cumplen su objetivo**.",
        "> Cada escenario se ejecutó con una carga nueva de los CSV (sin contaminación entre casos).",
        "",
        "## Tabla solicitada (5 columnas)",
        "",
        "| Caso | Estado inicial | Operación | Resultado real | Explicación |",
        "|---|---|---|---|---|",
    ]
    for r in resultados:
        estado_ini = f"{r.pedido_id}: {r.estado_inicial}, {r.unidades_inicial} u., {r.total_inicial} MXN"
        celdas = [r.caso_id, estado_ini, _operacion_legible(r), _resultado_legible(r), r.explicacion]
        lineas.append("| " + " | ".join(c.replace("|", "\\|") for c in celdas) + " |")
    lineas += [
        "",
        "## Esperado frente a observado",
        "",
        "| Caso | Pedido | Acción (CSV) | Objetivo (CSV) | Observado | Eventos al final | Unidades / total final | ¿Invariantes intactas en el rechazo? |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in resultados:
        eventos = ", ".join(r.eventos) if r.eventos else "(ninguno)"
        lineas.append(
            f"| {r.caso_id} | {r.pedido_id} | {r.accion} | {r.objetivo} | {r.resultado} | "
            f"{eventos} | {r.unidades_final} u. / {r.total_final} MXN | "
            f"{'sí' if r.invariantes_ok else 'NO'} |"
        )
    lineas += ["", "## Detalle de pasos", ""]
    for r in resultados:
        lineas.append(f"**{r.caso_id} · {r.pedido_id}** — {r.pista}")
        lineas.append("")
        for p in r.pasos:
            simbolo = "✔" if p.exito else "✘"
            evento = f" · evento `{p.evento}`" if p.evento else ""
            lineas.append(f"- {simbolo} {p.descripcion}: {p.detalle}{evento}")
        lineas.append("")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(lineas), encoding="utf-8")


def main(argv: list[str]) -> int:
    resultados = ejecutar_todos()
    for r in resultados:
        estado = "OK " if r.cumple else "FALLA"
        print(
            f"[{estado}] {r.caso_id} {r.pedido_id:<5} {r.accion:<30} "
            f"objetivo={r.objetivo:<20} observado={r.resultado:<20} "
            f"final={r.estado_final:<10} eventos={r.eventos}"
        )
    aprobados = sum(r.cumple for r in resultados)
    print(f"\n{aprobados}/{len(resultados)} escenarios cumplen su objetivo.")
    if "--bitacora" in argv:
        escribir_bitacora(resultados)
        print(f"Bitácora escrita en {BITACORA.relative_to(BASE)}")
    return 0 if aprobados == len(resultados) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
