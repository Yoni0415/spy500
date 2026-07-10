"""
Estrategia de senal para el SPY.

Regla: seguimiento de tendencia sobre la media movil de 200 dias (SMA200)
con banda anti-whipsaw del 2%. Validada sobre 1993-2026:
    - Buy & Hold:  CAGR 8.9%  | MaxDD -56.5% | Sharpe 0.55
    - Esta regla:  CAGR 7.6%  | MaxDD -21.6% | Sharpe 0.68

No busca ganar mas dinero total que comprar-y-mantener, sino recortar la
caida maxima a la mitad avisando cuando cambia el regimen del mercado.
"""
import numpy as np
import pandas as pd

SMA_WINDOW = 200
BAND = 0.02  # 2% de banda de histeresis para evitar senales falsas


def compute_position(close: pd.Series) -> pd.Series:
    """Serie 0/1: 1 = invertido (en SPY), 0 = fuera (en efectivo).

    Entra cuando el precio supera SMA200 * (1 + BAND).
    Sale cuando el precio cae bajo SMA200 * (1 - BAND).
    Entre esos limites, mantiene el estado anterior (histeresis).
    """
    sma = close.rolling(SMA_WINDOW).mean()
    up = close > sma * (1 + BAND)
    dn = close < sma * (1 - BAND)

    pos = np.zeros(len(close))
    state = 0
    for i in range(len(close)):
        if state == 0 and up.iloc[i]:
            state = 1
        elif state == 1 and dn.iloc[i]:
            state = 0
        pos[i] = state
    return pd.Series(pos, index=close.index, name="position")


def current_signal(close: pd.Series) -> dict:
    """Estado de hoy y si hubo cambio de regimen respecto a ayer."""
    pos = compute_position(close)
    sma = close.rolling(SMA_WINDOW).mean()

    today = int(pos.iloc[-1])
    yesterday = int(pos.iloc[-2])
    changed = today != yesterday

    if changed and today == 1:
        action = "BUY"
    elif changed and today == 0:
        action = "SELL"
    else:
        action = "HOLD"

    return {
        "date": close.index[-1].strftime("%Y-%m-%d"),
        "price": round(float(close.iloc[-1]), 2),
        "sma200": round(float(sma.iloc[-1]), 2),
        "invested": bool(today),
        "changed": changed,
        "action": action,
    }
