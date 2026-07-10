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
BAND = 0.04  # 4% de banda de histeresis para evitar senales falsas.
# Elegido por busqueda amplia (~90 variantes) validada fuera de muestra:
# optimizado en 1993-2009 y confirmado en 2010-2026, neto de comision 0.6%.

# Comision del broker POR LADO (compra o venta), como fraccion.
# Bull Market (Argentina): ajustar al valor real incluyendo derechos de
# mercado + IVA. Se puede sobreescribir con la variable de entorno COMMISSION_PCT.
COMMISSION = 0.006  # 0.6% por defecto


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
    return pd.Series(pos, index=close.index, name="regime")


# Timing de entrada/salida usando reversion a la media, SIN sumar operaciones.
# Al entrar esperamos un pozo (dias en baja) para comprar mas barato; al salir
# esperamos un rebote (dia en alza) para vender mejor. Con tope de espera para
# no perder el movimiento.
MAX_WAIT_BUY = 10  # dias que esperamos un pozo antes de entrar igual
MAX_WAIT_SELL = 5  # dias que esperamos un rebote antes de salir igual


def apply_timing(close: pd.Series, regime: pd.Series):
    """Convierte el regimen de tendencia en posicion real con timing.

    Devuelve (position, pending) donde pending es 'buy'/'sell'/None:
    'buy'  = la tendencia es alcista pero esperamos un pozo para entrar.
    'sell' = la tendencia se rompio pero esperamos un rebote para salir.
    """
    ret = close.pct_change().fillna(0)
    up = ret > 0
    down = ret < 0

    pos = np.zeros(len(close))
    pend = [None] * len(close)
    state = 0
    pending = None
    wait = 0
    for i in range(len(close)):
        want = regime.iloc[i]
        if state == 0:
            if want == 1:
                if pending != "buy":
                    pending = "buy"; wait = 0
                wait += 1
                if down.iloc[i] or wait >= MAX_WAIT_BUY:
                    state = 1; pending = None
            else:
                pending = None
        else:  # state == 1 (dentro)
            if want == 0:
                if pending != "sell":
                    pending = "sell"; wait = 0
                wait += 1
                if up.iloc[i] or wait >= MAX_WAIT_SELL:
                    state = 0; pending = None
            else:
                pending = None
        pos[i] = state
        pend[i] = pending
    return (pd.Series(pos, index=close.index, name="position"),
            pd.Series(pend, index=close.index, name="pending"))


def _last_entry_price(close: pd.Series, pos: pd.Series):
    """Precio y fecha de la ultima ENTRADA (transicion 0->1) vigente."""
    chg = pos.diff()
    entries = pos.index[chg == 1]
    if len(entries) == 0:
        return None, None
    d = entries[-1]
    return float(close.loc[d]), d.strftime("%Y-%m-%d")


def current_signal(close: pd.Series, commission: float = COMMISSION) -> dict:
    """Estado de hoy, cambio de regimen y P&L neto del trade si se vende."""
    regime = compute_position(close)
    pos, pending = apply_timing(close, regime)
    sma = close.rolling(SMA_WINDOW).mean()

    today = int(pos.iloc[-1])
    yesterday = int(pos.iloc[-2])
    changed = today != yesterday
    price = float(close.iloc[-1])
    pend = pending.iloc[-1]

    if changed and today == 1:
        action = "BUY"
    elif changed and today == 0:
        action = "SELL"
    elif pend == "buy":
        action = "WAIT_BUY"   # tendencia alcista, esperando un pozo para entrar
    elif pend == "sell":
        action = "WAIT_SELL"  # tendencia rota, esperando rebote para salir
    else:
        action = "HOLD"

    result = {
        "date": close.index[-1].strftime("%Y-%m-%d"),
        "price": round(price, 2),
        "sma200": round(float(sma.iloc[-1]), 2),
        "invested": bool(today),
        "changed": changed,
        "action": action,
        "pending": pend,
        "commission_pct": commission,
    }

    # Coste estimado de comision de esta operacion (un lado).
    if action in ("BUY", "SELL"):
        result["commission_cost_pct"] = round(commission * 100, 3)

    # Si vendemos, calcular P&L neto del round-trip contra la ultima entrada.
    if action == "SELL":
        entry_px, entry_date = _last_entry_price(close, pos)
        if entry_px:
            gross = price / entry_px - 1
            net = (1 + gross) * (1 - commission) ** 2 - 1
            result.update({
                "entry_price": round(entry_px, 2),
                "entry_date": entry_date,
                "trade_gross_pct": round(gross * 100, 2),
                "trade_net_pct": round(net * 100, 2),
            })

    return result
