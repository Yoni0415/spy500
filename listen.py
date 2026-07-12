"""
Escucha mensajes de Telegram y responde bajo demanda con la senal del dia.

Le escribis al bot un codigo (por defecto "999") y te contesta al toque
(en la proxima corrida, cada 5-10 minutos) con la misma senal que te daria
el aviso automatico diario. Ignora mensajes de cualquier chat que no sea
el tuyo (TELEGRAM_CHAT_ID).

No necesita guardar estado entre corridas: usa el mecanismo de "offset" de
la API de Telegram (getUpdates) para marcar los mensajes como leidos del
lado del servidor de Telegram, asi que cada corrida es independiente.

Variables de entorno (las mismas que agent.py):
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID
    TRIGGER_CODE   codigo que activa la respuesta (default "999")
"""
import os
import sys

import requests

from agent import build_report, send_telegram
from portfolio import apply_command, AYUDA

MENU = "\n\n————\n\U0001F4CB <b>Menú</b>\n" + AYUDA

TRIGGER_CODE = os.environ.get("TRIGGER_CODE") or "999"


def get_updates(token: str):
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()["result"]


def confirm_read(token: str, up_to_update_id: int):
    """Le dice a Telegram que ya procesamos hasta este update_id."""
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    requests.get(url, params={"offset": up_to_update_id + 1}, timeout=30)


def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    allowed_chat_id = os.environ["TELEGRAM_CHAT_ID"]

    updates = get_updates(token)
    if not updates:
        print("Sin mensajes nuevos.")
        return

    max_update_id = max(u["update_id"] for u in updates)
    answered = 0

    for u in updates:
        msg = u.get("message") or u.get("edited_message")
        if not msg or "text" not in msg:
            continue
        chat_id = str(msg["chat"]["id"])
        text = msg["text"].strip()

        if chat_id != str(allowed_chat_id):
            print(f"Ignorado: mensaje de chat no autorizado ({chat_id}).")
            continue

        if text == TRIGGER_CODE:
            report, _ = build_report(log=False)
            send_telegram(report + MENU, chat_id=chat_id)
            answered += 1
            print(f"Respondido a codigo '{TRIGGER_CODE}'.")
            continue

        reply = apply_command(text)
        if reply:
            # AYUDA ya es el menu; a lo demas se le agrega al pie
            if reply != AYUDA:
                reply += MENU
            send_telegram(reply, chat_id=chat_id)
            answered += 1
            print(f"Comando de cartera procesado: {text.split()[0].upper()}")
        else:
            # Mensaje no reconocido: responder con el menu para guiar
            send_telegram("No reconocí ese comando." + MENU, chat_id=chat_id)
            answered += 1
            print(f"Mensaje no reconocido, se envio el menu: {text!r}")

    # Marcar todo como leido para no reprocesarlo en la proxima corrida.
    confirm_read(token, max_update_id)
    print(f"{len(updates)} mensaje(s) revisados, {answered} respondido(s).")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERROR:", repr(e), file=sys.stderr)
        sys.exit(1)
