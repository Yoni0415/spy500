# spy500

Agente que notifica por Telegram cuando cambia el regimen de tendencia del
SPY (S&P 500), para proteger capital en las caidas grandes.

## Idea

No se puede predecir si el SPY sube o baja *manana* (es ruido: ~54% de acierto
= moneda al aire). Lo que si funciona es **detectar cambios de regimen**: estar
invertido solo cuando el precio esta sobre su media movil de 200 dias, con una
banda del 2% para evitar senales falsas.

Sobre ese nucleo se agrega **timing de reversion a la media** sin sumar
operaciones: al entrar espera un pozo (dias en baja) para comprar mas barato, y
al salir espera un rebote (dia verde) para vender mejor. La reversion pura no se
usa como estrategia porque su edge (~0.1-0.3% por trade) no sobrevive a la
comision de Bull Market (~0.6% por lado); solo sirve para afinar el precio.

Validado sobre 1993-2026, **neto de comision (0.6%/operacion)**:

| Estrategia         | CAGR | Caida maxima | Sharpe |
|--------------------|------|--------------|--------|
| Comprar y mantener | 8.9% | **-56.5%**   | 0.55   |
| Tendencia + timing | 6.7% | **-24.7%**   | 0.60   |

No gana mas dinero total, pero **corta la caida maxima a la mitad** y da mejor
retorno ajustado por riesgo. Genera ~1 senal al ano (comisiones despreciables).

## Archivos

- `strategy.py` — logica de la senal (SMA200 + banda 2%).
- `agent.py` — descarga SPY, calcula senal y avisa por Telegram.
- `backtest.py` — reproduce la tabla de arriba con el CSV local.
- `.github/workflows/daily-signal.yml` — corre el agente cada dia habil.

## Puesta en marcha

1. Crear un bot con [@BotFather](https://t.me/BotFather) (`/newbot`) -> token.
2. Obtener tu chat id con [@userinfobot](https://t.me/userinfobot).
3. En el repo: **Settings -> Secrets and variables -> Actions** y agregar:
   - Secret `TELEGRAM_BOT_TOKEN`
   - Secret `TELEGRAM_CHAT_ID`
   - (opcional) Variable `ALWAYS_NOTIFY = 1` para recibir el estado cada dia.
4. Probar a mano en la pestana **Actions -> Senal diaria SPY -> Run workflow**.

## Backtest local

```bash
pip install -r requirements.txt
python backtest.py
```

> Aviso: esto es una herramienta de analisis, no asesoramiento financiero.
> Rendimientos pasados no garantizan resultados futuros.
