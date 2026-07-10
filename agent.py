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

from strategy import current_signal, BAND, COMMISSION


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
    resp.raise_for_status()


def build_message(sig: dict) -> str:
    trend = "sobre" if sig["invested"] else "bajo"
    comm = sig.get("commission_cost_pct")
    if sig["action"] == "BUY":
        return (
            f"\U0001F7E2 <b>SENAL: COMPRAR / ENTRAR</b>\n\n"
            f"El SPY recupero su tendencia (cruzo <b>sobre</b> la SMA200 +{BAND:.0%}).\n"
            f"Fecha: {sig['date']}\n"
            f"Precio: ${sig['price']}  |  SMA200: ${sig['sma200']}\n"
            f"Comision estimada de compra: ~{comm}%\n\n"
            f"Regimen alcista: reentrar en SPY."
        )
    if sig["action"] == "SELL":
        pl = ""
        if "trade_net_pct" in sig:
            signo = "GANANCIA" if sig["trade_net_pct"] >= 0 else "PERDIDA"
            pl = (
                f"\nEntrada: ${sig['entry_price']} ({sig['entry_date']})\n"
                f"Resultado del trade: {sig['trade_gross_pct']:+}% bruto  |  "
                f"<b>{sig['trade_net_pct']:+}% neto</b> de comisiones ({signo})"
            )
        return (
            f"\U0001F534 <b>SENAL: VENDER / REDUCIR</b>\n\n"
            f"El SPY perdio su tendencia (cruzo <b>bajo</b> la SMA200 -{BAND:.0%}).\n"
            f"Fecha: {sig['date']}\n"
            f"Precio: ${sig['price']}  |  SMA200: ${sig['sma200']}\n"
            f"Comision estimada de venta: ~{comm}%{pl}\n\n"
            f"Regimen bajista: salir a efectivo para proteger capital."
        )
    if sig["action"] == "WAIT_BUY":
        return (
            f"\U0001F7E1 <b>Tendencia alcista — esperando pozo para entrar</b>\n"
            f"{sig['date']}  ${sig['price']} sobre SMA200 ${sig['sma200']}\n"
            f"Aun en efectivo. El agente comprara en la proxima baja "
            f"(o a mas tardar en pocos dias)."
        )
    if sig["action"] == "WAIT_SELL":
        return (
            f"\U0001F7E0 <b>Tendencia rota — esperando rebote para salir</b>\n"
            f"{sig['date']}  ${sig['price']} bajo SMA200 ${sig['sma200']}\n"
            f"Aun invertido. El agente vendera en el proximo dia verde "
            f"(o a mas tardar en pocos dias)."
        )
    # HOLD (latido diario)
    estado = "INVERTIDO \U0001F7E2" if sig["invested"] else "EN EFECTIVO \U0001F534"
    return (
        f"⚙️ Estado diario SPY ({sig['date']})\n"
        f"Precio ${sig['price']} {trend} SMA200 ${sig['sma200']}\n"
        f"Posicion actual: {estado}. Sin cambios."
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
