"""
Backtest reproducible: compara la estrategia contra comprar-y-mantener
usando el CSV historico local del SPY. Ejecutar:  python backtest.py
"""
import numpy as np
import pandas as pd

from strategy import compute_position


def load_close(path="spy_historico_completo.csv"):
    d = pd.read_csv(path, header=[0, 1], index_col=0, parse_dates=True)
    d.columns = d.columns.get_level_values(0)
    return d["Close"].dropna()


def stats(returns):
    eq = (1 + returns).cumprod()
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1
    maxdd = (eq / eq.cummax() - 1).min()
    sharpe = returns.mean() / returns.std() * np.sqrt(252)
    return cagr, maxdd, sharpe


def main():
    close = load_close()
    ret = close.pct_change().fillna(0)
    pos = compute_position(close)

    bh = ret
    # La posicion se decide con el cierre de hoy y se ejecuta al dia siguiente:
    # aplicamos pos con un dia de retraso para evitar sesgo de lookahead.
    strat = pos.shift(1).fillna(0) * ret

    print(f"Periodo: {close.index[0].date()} a {close.index[-1].date()}\n")
    print(f"{'Estrategia':<18}{'CAGR':>8}{'MaxDD':>9}{'Sharpe':>8}")
    for name, r in [("Buy & Hold", bh), ("Tendencia+banda", strat)]:
        c, d, s = stats(r)
        print(f"{name:<18}{c*100:>7.1f}%{d*100:>8.1f}%{s:>8.2f}")

    trades = int((pos.diff().abs() > 0).sum())
    print(f"\nCambios de posicion: {trades}  |  Dias invertido: {pos.mean()*100:.0f}%")


if __name__ == "__main__":
    main()
