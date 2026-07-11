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
"""
import os
import sys

import requests
import yfinance as yf

from strategy import current_signal, COMMISSION


def fetch_spy_close():
    data = yf.download("SPY", period="max", interval="1d",
                       auto_adjust=False, progress=False)
    if data.empty:
        raise RuntimeError("Descarga de SPY vacia")
    close = data["Close"]
    if hasattr(close, "columns"):  # yfinance devuelve MultiIndex a veces
        close = close.iloc[:, 0]
    return close.dropna()


def send_telegram(text: str):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, data={
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"Telegram {resp.status_code}: {resp.text}")


def build_message(sig: dict) -> str:
    trend = "sobre" if sig["invested"] else "bajo"
    comm = sig.get("commission_cost_pct")

    if sig["action"] == "BUY":
        return (
            f"\U0001F7E2 <b>Jonah: comprá todo el SPY mañana a la apertura.</b>\n\n"
            f"El mercado volvió a tendencia alcista.\n"
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
            f"\U0001F534 <b>Jonah: vendé todo el SPY mañana a la apertura.</b>\n\n"
            f"El mercado rompió tendencia alcista, mejor salir a efectivo.\n"
            f"Precio: ${sig['price']}  (SMA200: ${sig['sma200']})\n"
            f"Comisión estimada: ~{comm}%{pl}"
        )

    if sig["action"] == "WAIT_BUY":
        return (
            f"\U0001F7E1 <b>Jonah: todavía no compres, esperá una baja para entrar mejor.</b>\n\n"
            f"Tendencia alcista confirmada (${sig['price']} sobre SMA200 ${sig['sma200']}), "
            f"pero conviene esperar un pozo de precio antes de entrar. "
            f"Te aviso apenas sea momento (a más tardar en pocos días)."
        )

    if sig["action"] == "WAIT_SELL":
        return (
            f"\U0001F7E0 <b>Jonah: todavía no vendas, esperá un rebote para salir mejor.</b>\n\n"
            f"Tendencia rota (${sig['price']} bajo SMA200 ${sig['sma200']}), "
            f"pero conviene esperar un día de suba antes de salir. "
            f"Te aviso apenas sea momento (a más tardar en pocos días)."
        )

    # HOLD (latido diario)
    if sig["invested"]:
        return (
            f"\U0001F7E2 <b>Jonah: no hagas nada, seguí invertido en el SPY.</b>\n"
            f"${sig['price']} {trend} SMA200 ${sig['sma200']}. Sin cambios."
        )
    return (
        f"\U0001F534 <b>Jonah: no hagas nada, seguí en efectivo.</b>\n"
        f"${sig['price']} {trend} SMA200 ${sig['sma200']}. Sin cambios."
    )


def main():
    commission = float(os.environ.get("COMMISSION_PCT") or COMMISSION)
    close = fetch_spy_close()
    sig = current_signal(close, commission=commission)
    print("Senal:", sig)

    always = os.environ.get("ALWAYS_NOTIFY", "0") == "1"
    if sig["changed"] or always:
        send_telegram(build_message(sig))
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
