"""
Contabilidad de la cartera real, cifrada para poder vivir en un repo publico.

El estado (posiciones, efectivo, objetivo, historial de operaciones) se guarda
en portfolio.enc, cifrado con Fernet (AES). La clave vive SOLO en el secret
PORTFOLIO_KEY de GitHub Actions: el archivo commiteado es ilegible sin ella.
Nunca commitear portfolio.json (plaintext) — esta en .gitignore.

El usuario actualiza su cartera escribiendole al bot de Telegram:
    COMPRE SPY 10 19720      compre 10 CEDEARs de SPY a ARS 19.720 c/u
    VENDI QQQ 23 56750       vendi 23 CEDEARs de QQQ a ARS 56.750 c/u
    INGRESO 500000           ingrese ARS 500.000 de efectivo fresco
    RETIRO 100000            retire ARS 100.000
    OBJETIVO 6000000         fijar objetivo de cartera en ARS 6.000.000
    POS                      ver la cartera valuada a precios de hoy
    AYUDA                    lista de comandos

Los precios se manejan en ARS (lo que muestra Bull Market). La valuacion usa
los tickers .BA de BYMA via Yahoo Finance (precio del CEDEAR en pesos).
"""
import json
import os
from datetime import date

import yfinance as yf
from cryptography.fernet import Fernet

from strategy import COMMISSION

STATE_FILE = os.path.join(os.path.dirname(__file__), "portfolio.enc")

AYUDA = (
    "Comandos de cartera:\n"
    "COMPRE [ticker] [cantidad] [precio ARS]\n"
    "VENDI [ticker] [cantidad] [precio ARS]\n"
    "INGRESO [monto ARS]  |  RETIRO [monto ARS]\n"
    "OBJETIVO [monto ARS]\n"
    "POS — ver cartera  |  999 — señales del día"
)


def _fernet():
    key = os.environ.get("PORTFOLIO_KEY")
    return Fernet(key.encode()) if key else None


def load_portfolio():
    f = _fernet()
    if f is None or not os.path.exists(STATE_FILE):
        return None
    with open(STATE_FILE, "rb") as fh:
        return json.loads(f.decrypt(fh.read()))


def save_portfolio(p):
    f = _fernet()
    if f is None:
        raise RuntimeError("Falta PORTFOLIO_KEY")
    with open(STATE_FILE, "wb") as fh:
        fh.write(f.encrypt(json.dumps(p).encode()))


def cedear_price_ars(ticker: str) -> float:
    d = yf.download(f"{ticker}.BA", period="5d", interval="1d", progress=False)
    close = d["Close"]
    if hasattr(close, "columns"):
        close = close.iloc[:, 0]
    return float(close.dropna().iloc[-1])


def valuation(p) -> str:
    lines = ["\U0001F4BC <b>Tu cartera hoy</b>"]
    total = p["cash_ars"]
    for t, pos in sorted(p["positions"].items()):
        try:
            px = cedear_price_ars(t)
        except Exception:
            px = pos["ppc_ars"]  # fallback: valuar al PPC si falla el precio
        val = pos["qty"] * px
        total += val
        pl = (px / pos["ppc_ars"] - 1) * 100
        lines.append(
            f"{t}: {pos['qty']:g} u. × ARS {px:,.0f} = ARS {val:,.0f} "
            f"({pl:+.1f}% vs tu PPC {pos['ppc_ars']:,.0f})"
        )
    lines.append(f"Efectivo disponible: ARS {p['cash_ars']:,.0f}")
    lines.append(f"<b>Total: ARS {total:,.0f}</b>")
    if p.get("target_ars"):
        pct = total / p["target_ars"] * 100
        lines.append(f"Objetivo ARS {p['target_ars']:,.0f}: {pct:.1f}% alcanzado")
    return "\n".join(lines)


def apply_command(text: str):
    """Procesa un comando de cartera. Devuelve respuesta o None si no lo es."""
    parts = text.strip().upper().split()
    if not parts:
        return None
    cmd = parts[0]

    if cmd == "AYUDA":
        return AYUDA
    if cmd not in ("POS", "CARTERA", "COMPRE", "VENDI", "INGRESO",
                   "RETIRO", "OBJETIVO"):
        return None

    p = load_portfolio()
    if p is None:
        return "No hay cartera configurada (falta PORTFOLIO_KEY o portfolio.enc)."

    try:
        if cmd in ("POS", "CARTERA"):
            return valuation(p)

        if cmd in ("COMPRE", "VENDI"):
            ticker, qty, price = parts[1], float(parts[2]), float(parts[3])
            cost = qty * price
            fee = cost * COMMISSION
            if cmd == "COMPRE":
                if cost + fee > p["cash_ars"] + 1:  # margen por redondeo
                    return (f"Ojo: registraste una compra de ARS {cost+fee:,.0f} "
                            f"pero el efectivo era ARS {p['cash_ars']:,.0f}. "
                            f"La registro igual (efectivo queda negativo, corregilo).")
                pos = p["positions"].get(ticker, {"qty": 0, "ppc_ars": 0})
                new_qty = pos["qty"] + qty
                pos["ppc_ars"] = (pos["qty"] * pos["ppc_ars"] + cost) / new_qty
                pos["qty"] = new_qty
                p["positions"][ticker] = pos
                p["cash_ars"] -= cost + fee
                verb = "Compra registrada"
            else:
                pos = p["positions"].get(ticker)
                if not pos or pos["qty"] < qty:
                    return f"No tenés {qty:g} de {ticker} (tenés {pos['qty'] if pos else 0:g})."
                pl = (price / pos["ppc_ars"] - 1) * 100
                pos["qty"] -= qty
                if pos["qty"] == 0:
                    del p["positions"][ticker]
                p["cash_ars"] += cost - fee
                verb = f"Venta registrada ({pl:+.1f}% vs tu PPC)"
            p["trades"].append({"date": date.today().isoformat(), "cmd": cmd,
                                "ticker": ticker, "qty": qty, "price_ars": price})
            save_portfolio(p)
            return (f"✅ {verb}: {qty:g} {ticker} a ARS {price:,.0f} "
                    f"(comisión ~ARS {fee:,.0f}).\n"
                    f"Efectivo: ARS {p['cash_ars']:,.0f}")

        if cmd in ("INGRESO", "RETIRO"):
            monto = float(parts[1])
            p["cash_ars"] += monto if cmd == "INGRESO" else -monto
            save_portfolio(p)
            return (f"✅ {cmd.title()} de ARS {monto:,.0f} registrado. "
                    f"Efectivo disponible: ARS {p['cash_ars']:,.0f}")

        if cmd == "OBJETIVO":
            p["target_ars"] = float(parts[1])
            save_portfolio(p)
            return f"✅ Objetivo fijado en ARS {p['target_ars']:,.0f}."

    except (IndexError, ValueError):
        return f"No entendí el comando. Formato:\n{AYUDA}"
