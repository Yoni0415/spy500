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

Parametros finales (SMA200, banda 4%, esperas 10/5) elegidos por busqueda
amplia (~90 variantes) con validacion fuera de muestra: optimizados en
1993-2009 y confirmados en 2010-2026.

Validado sobre 1993-2026, **neto de comision (0.6%/operacion)**:

| Estrategia         | CAGR | Caida maxima | Sharpe |
|--------------------|------|--------------|--------|
| Comprar y mantener | 8.9% | **-56.5%**   | 0.55   |
| Tendencia + timing | 8.1% | **-19.0%**   | 0.68   |

14 operaciones en 33 anios: 79% ganadoras, ganancia media +30.5%, perdida
media -2.9%, peor trade -6.8%. Casi el mismo retorno que comprar y mantener
con **un tercio de la caida maxima**.

## Archivos

- `strategy.py` — logica de la senal (SMA200 + banda 4% + timing 10/5).
- `agent.py` — descarga SPY, calcula senal y avisa por Telegram (aviso diario).
- `listen.py` — responde bajo demanda cuando le escribis un codigo al bot.
- `backtest.py` — reproduce la tabla de arriba con el CSV local.
- `.github/workflows/daily-signal.yml` — corre el aviso diario cada dia habil.
- `.github/workflows/listen.yml` — revisa mensajes nuevos cada ~10 minutos.

## Puesta en marcha

1. Crear un bot con [@BotFather](https://t.me/BotFather) (`/newbot`) -> token.
2. Obtener tu chat id con [@userinfobot](https://t.me/userinfobot).
3. Abrirle el chat a tu bot (boton **Start** o mandarle cualquier mensaje):
   sin esto Telegram no deja que el bot te escriba.
4. En el repo: **Settings -> Secrets and variables -> Actions** y agregar:
   - Secret `TELEGRAM_BOT_TOKEN`
   - Secret `TELEGRAM_CHAT_ID`
   - (opcional) Variable `ALWAYS_NOTIFY = 1` para recibir el estado cada dia.
   - (opcional) Variable `TRIGGER_CODE` para cambiar el codigo de consulta
     bajo demanda (default `999`).
5. Probar a mano en la pestana **Actions -> Senal diaria SPY -> Run workflow**.

## Consulta bajo demanda

Escribile a tu bot el codigo `999` (o el que hayas configurado en
`TRIGGER_CODE`) y te responde con la senal de ese dia — la misma que te
llegaria en el aviso automatico. Tarda hasta ~10 minutos porque
`listen.yml` revisa mensajes nuevos en ese intervalo, no al instante.

## Cartera real (cifrada)

El agente lleva la contabilidad de la cartera: posiciones, PPC, efectivo
disponible y objetivo. El estado vive en `portfolio.enc`, cifrado con
Fernet/AES — el repo es publico pero el archivo es ilegible sin la clave,
que existe solo en el secret `PORTFOLIO_KEY`. El plaintext
(`portfolio.json`) esta en `.gitignore` y nunca se commitea.

Comandos por Telegram (los procesa `listen.yml` cada ~10 min):

```
COMPRE SPY 10 19720     compre 10 CEDEARs de SPY a ARS 19.720 c/u
VENDI QQQ 23 56750      vendi 23 CEDEARs de QQQ a ARS 56.750 c/u
INGRESO 500000          ingrese efectivo fresco (ARS)
RETIRO 100000           retire efectivo (ARS)
OBJETIVO 6000000        fijar objetivo de cartera (ARS)
POS                     ver la cartera valuada a precios de hoy
AYUDA                   lista de comandos
```

La valuacion usa los precios de los CEDEARs en BYMA (tickers `.BA` de
Yahoo Finance, en pesos). Las senales de estrategia siguen usando el
precio en USD del ETF subyacente.

## Activos seguidos y diversificacion

`SPY`, `QQQ` y `GLD`. Datos (correlacion de retornos diarios con SPY,
10 anios): QQQ +0.93 (casi duplicado de SPY), GLD +0.10 (diversificador
real). XLE/EEM/EWZ se evaluaron y descartaron: la estrategia rinde mal en
ellos y sus caidas maximas son enormes. En QQQ la estrategia corta la
caida maxima de -83% a -44% (1999-2026); en GLD tambien funciona
(CAGR 7.5% neto, DD -42%).

## Historial de senales

Cada corrida del aviso diario (`daily-signal.yml`) agrega una fila a
`signals_log.csv` con la senal real de ese dia, y el workflow la commitea
de vuelta al repo. Sirve para dos cosas:

- **Trackear en vivo** lo que el sistema predijo contra lo que paso de
  verdad, sin depender solo del backtest historico.
- **Mantener el repo "activo"**: GitHub apaga los workflows programados
  despues de 60 dias sin actividad, y correr el cron por si solo no cuenta
  como actividad — hace falta un commit real, que es justo lo que este
  paso genera automaticamente.

## Repo publico vs privado

Si el repo es **privado**, GitHub factura los minutos de Actions
redondeados al minuto por corrida. Con `listen.yml` cada 10 minutos, eso
suma ~4.300 min/mes contra 2.000 gratis — puede generar costo. Si el repo
es **publico**, los runners estandar de GitHub Actions son gratis e
ilimitados (no hay nada sensible en el codigo; las credenciales viven en
Secrets, que quedan ocultos aunque el repo sea publico).

## Backtest local

```bash
pip install -r requirements.txt
python backtest.py
```

> Aviso: esto es una herramienta de analisis, no asesoramiento financiero.
> Rendimientos pasados no garantizan resultados futuros.
