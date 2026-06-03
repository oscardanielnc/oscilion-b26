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

🟢 Fases 1-4 completas: base del sistema, datos (sin look-ahead), motor de análisis (rangos, régimen, reversión, score 0-100, riesgo L=2%/stop) y backtest honesto (walk-forward + costos reales + go/no-go). Veredicto inicial de la lógica naïve: NO-GO — falta la confirmación de giro (Fase 5) y validación multi-año. Siguiente: Fase 5 (motor en vivo).

## Stack

Python · ccxt · SQLite · FastAPI · React + lightweight-charts. Despliegue: VM Oracle + systemd + `deploy.sh`.
