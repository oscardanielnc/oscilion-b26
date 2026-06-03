# Oscilion 📈

Bot de trading intradía de cripto (Binance perpetuos) basado en **reversión dentro de rangos** con detección de régimen, gestión de riesgo estricta y backtest honesto.

**Norte:** monitor en vivo → bot 100% automático → copy-lead en Binance.

## En una frase

Descubrir el rango en el que oscila cada moneda (BTC, ETH, SOL…), entrar cerca de un borde *con confirmación de giro*, salir en el opuesto, y proteger con un stop anti-barridas — operando solo lo predecible, con riesgo fijo del 2% por trade.

## Documentación

| Doc | Contenido |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Acuerdos de trabajo e invariantes |
| [`docs/VISION.md`](docs/VISION.md) | Qué, por qué, filosofía, go/no-go |
| [`docs/RISK_MODEL.md`](docs/RISK_MODEL.md) | Matemática de riesgo, apalancamiento, sizing, stops |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Estructura, módulos, datos, ops, resiliencia |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Fases con entregables |

## Estado

🟢 Fases 1-5 completas: base, datos (sin look-ahead), motor de análisis, backtest honesto y motor en vivo (máquina de estados con confirmación de giro, gestión de salida, calibración forward, alertas ENTRA/TOMA/SAL). La confirmación de giro da vuelta el edge en backtest (Sharpe −0.47 → +1.89 en 1h/~120d); prometedor pero aún no confirmado (falta validación multi-año). Siguiente: Fase 6 (frontend).

## Stack

Python · ccxt · SQLite · FastAPI · React + lightweight-charts. Despliegue: VM Oracle + systemd + `deploy.sh`.
