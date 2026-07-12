"""
Agente diario: descarga el SPY, calcula la senal y notifica por Telegram.

Se ejecuta en GitHub Actions una vez al dia tras el cierre del mercado.
Es sin estado: recalcula toda la serie desde 1993 y detecta si HOY cambio
el regimen respecto a ayer. Solo alerta en cambios (BUY/SELL). Los dias
normales manda un latido corto para confirmar que el agente sigue vivo.

Variables de entorno (GitHub Secrets):
    TELEGRAM_BOT_TOKEN   token de @BotFather
    TELEGRAM_CHAT_ID     tu chat id de @userinfobot
    ALWAYS_NOTIFY        "1" para recibir el estado diario aunque no haya cambio

Cada corrida agrega un registro a signals_log.csv (historial real de
senales, no backtest). El workflow lo commitea de vuelta al repo, lo que
ademas mantiene el repositorio "activo" y evita que GitHub desactive los
workflows programados por 60 dias de inactividad.

Ver tambien listen.py: responde bajo demanda cuando le escribis un codigo
al bot (ej. "999"), sin esperar al aviso automatico diario.
"""
import csv
import os
import sys

import requests
import yfinance as yf

from strategy import current_signal, COMMISSION

TICKERS = ["SPY", "QQQ"]  # activos de la cartera que sigue el agente

SIGNALS_LOG = os.path.join(os.path.dirname(__file__), "signals_log.csv")
LOG_FIELDS = [
    "date", "ticker", "action", "price", "sma200", "invested", "changed",
    "commission_pct", "commission_cost_pct",
    "entry_price", "entry_date", "trade_gross_pct", "trade_net_pct",
]


def fetch_close(ticker: str):
    data = yf.download(ticker, period="max", interval="1d",
                       auto_adjust=False, progress=False)
    if data.empty:
        raise RuntimeError(f"Descarga de {ticker} vacia")
    close = data["Close"]
    if hasattr(close, "columns"):  # yfinance devuelve MultiIndex a veces
        close = close.iloc[:, 0]
    return close.dropna()


def send_telegram(text: str, chat_id: str = None):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = chat_id or os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, data={
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"Telegram {resp.status_code}: {resp.text}")


def get_signal(ticker: str = "SPY", commission: float = None) -> dict:
    commission = commission if commission is not None else float(
        os.environ.get("COMMISSION_PCT") or COMMISSION)
    close = fetch_close(ticker)
    sig = current_signal(close, commission=commission)
    sig["ticker"] = ticker
    return sig


def log_signal(sig: dict):
    """Agrega la senal de hoy a signals_log.csv (historial real, no backtest).

    Idempotente: si ya hay un registro para esta fecha y ticker, no duplica
    (para poder correr el agente varias veces el mismo dia sin ensuciar
    el historial).
    """
    file_exists = os.path.exists(SIGNALS_LOG)
    if file_exists:
        with open(SIGNALS_LOG, encoding="utf-8") as f:
            lines = f.read().strip().splitlines()
        if lines and lines[0] != ",".join(LOG_FIELDS):
            # migrar formato viejo (sin columna ticker): esas filas eran de SPY
            header_old = lines[0].split(",")
            new_lines = [",".join(LOG_FIELDS)]
            for ln in lines[1:]:
                vals = dict(zip(header_old, ln.split(",")))
                vals["ticker"] = "SPY"
                new_lines.append(",".join(vals.get(k, "") for k in LOG_FIELDS))
            with open(SIGNALS_LOG, "w", newline="", encoding="utf-8") as f:
                f.write("\n".join(new_lines) + "\n")
            lines = new_lines
        key = f"{sig['date']},{sig['ticker']}"
        if any(ln.startswith(key) for ln in lines[1:]):
            print(f"Ya habia registro para {key}, no se duplica.")
            return

    with open(SIGNALS_LOG, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow({k: sig.get(k, "") for k in LOG_FIELDS})
    print(f"Senal registrada: {sig['ticker']} {sig['date']}.")


def build_message(sig: dict) -> str:
    t = sig.get("ticker", "SPY")
    trend = "sobre" if sig["invested"] else "bajo"
    comm = sig.get("commission_cost_pct")

    if sig["action"] == "BUY":
        return (
            f"\U0001F7E2 <b>Jonah: comprá todo el {t} mañana a la apertura.</b>\n\n"
            f"El {t} volvió a tendencia alcista.\n"
            f"Precio: ${sig['price']}  (SMA200: ${sig['sma200']})\n"
            f"Comisión estimada: ~{comm}%"
        )

    if sig["action"] == "SELL":
        pl = ""
        if "trade_net_pct" in sig:
            signo = "ganancia" if sig["trade_net_pct"] >= 0 else "pérdida"
            pl = (
                f"\n\nEntraste el {sig['entry_date']} a ${sig['entry_price']}.\n"
                f"Resultado neto de este trade: <b>{sig['trade_net_pct']:+}%</b> ({signo})."
            )
        return (
            f"\U0001F534 <b>Jonah: vendé todo el {t} mañana a la apertura.</b>\n\n"
            f"El {t} rompió tendencia alcista, mejor salir a efectivo.\n"
            f"Precio: ${sig['price']}  (SMA200: ${sig['sma200']})\n"
            f"Comisión estimada: ~{comm}%{pl}"
        )

    if sig["action"] == "WAIT_BUY":
        return (
            f"\U0001F7E1 <b>Jonah: todavía no compres {t}, esperá una baja para entrar mejor.</b>\n\n"
            f"Tendencia alcista confirmada (${sig['price']} sobre SMA200 ${sig['sma200']}), "
            f"pero conviene esperar un pozo de precio antes de entrar. "
            f"Te aviso apenas sea momento (a más tardar en pocos días)."
        )

    if sig["action"] == "WAIT_SELL":
        return (
            f"\U0001F7E0 <b>Jonah: todavía no vendas {t}, esperá un rebote para salir mejor.</b>\n\n"
            f"Tendencia rota (${sig['price']} bajo SMA200 ${sig['sma200']}), "
            f"pero conviene esperar un día de suba antes de salir. "
            f"Te aviso apenas sea momento (a más tardar en pocos días)."
        )

    # HOLD (latido diario)
    if sig["invested"]:
        return (
            f"\U0001F7E2 <b>{t}: no hagas nada, seguí invertido.</b>\n"
            f"${sig['price']} {trend} SMA200 ${sig['sma200']}. Sin cambios."
        )
    return (
        f"\U0001F534 <b>{t}: no hagas nada, seguí en efectivo.</b>\n"
        f"${sig['price']} {trend} SMA200 ${sig['sma200']}. Sin cambios."
    )


def build_report() -> tuple:
    """Senales de todos los tickers. Devuelve (texto_combinado, hubo_cambio)."""
    parts = []
    any_changed = False
    for t in TICKERS:
        sig = get_signal(t)
        print("Senal:", sig)
        log_signal(sig)
        parts.append(build_message(sig))
        any_changed = any_changed or sig["changed"]
    return "\n\n".join(parts), any_changed


def main():
    text, any_changed = build_report()

    always = os.environ.get("ALWAYS_NOTIFY", "0") == "1"
    if any_changed or always:
        send_telegram(text)
        print("Notificacion enviada.")
    else:
        print("Sin cambio de regimen; no se notifica (ALWAYS_NOTIFY=0).")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Intenta avisar del fallo por Telegram; si no, sale con error.
        try:
            send_telegram(f"⚠️ El agente SPY fallo: {e!r}")
        except Exception:
            pass
        print("ERROR:", repr(e), file=sys.stderr)
        sys.exit(1)
