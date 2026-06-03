# Oscilion — Guía para sesiones de Claude

> Bot de trading intradía de cripto (Binance perpetuos) basado en **reversión dentro de rangos** con detección de régimen, gestión de riesgo estricta y backtest honesto. Norte: **bot 100% automático + copy-lead en Binance**.

## ⚙️ Acuerdos de trabajo (LEER SIEMPRE)

| Regla | Detalle |
|---|---|
| 🚫 **NO hago `git push`** | El usuario hace los push (pide credenciales). Yo **sí hago `git commit`**. |
| ✅ **Autorización autónoma** | Estoy autorizado a leer web, editar archivos y ejecutar lo necesario **sin preguntar**. No frenar la ejecución por confirmaciones. El usuario a veces no está mirando el chat. |
| 🗣️ **Lenguaje conciso y visual** | Reportes cortos, claros, con tablas/emojis/diagramas. Nada redundante. El usuario es ing. informático y sabe matemáticas; es visual. Explayarme solo si lo pide. |
| 🖥️ **Despliegue** | VM de Oracle (junto a otros proyectos, p.ej. `kepler`). systemd + `deploy.sh` de un comando. |
| 🧱 **Calidad base** | Arquitectura que soporte TODO desde el inicio: eficiencia, integridad, buena organización de funciones y datos. Servicio resiliente: captura errores, se reinicia solo, NO muere, logs persistentes. |

## 🔒 Invariantes del sistema (no romper sin discutir)

- **Riesgo por trade ≤ 2%** del capital de ESE trade. **Meta ≥ 5%** (piso, no techo). Filtro de entrada **RR ≥ 2.5**.
- **Apalancamiento = 2% ÷ distancia_stop(%)** → pérdida fija 2%, liquidación ~50× más lejos que el stop.
- **Stop anti-barridas**: más allá del clúster de liquidez + buffer ATR. Nunca en el nivel obvio.
- **Solo operar lo predecible**: régimen rango o canal diagonal limpio. Si no hay claridad → **no operar**.
- **Maker cuando conviene y es seguro; taker cuando hay urgencia** (stop / ruptura en contra).
- **Todo es auditable**: cada snapshot, predicción, decisión, trade y set de parámetros persiste (append-only).
- **Honestidad / go-no-go**: el backtest puede decir "no hay edge" → se acepta. Iterar con evidencia, no con manotazos.

## 🧰 Stack

Python (pandas, numpy, scipy, statsmodels) · `ccxt` (Binance) · SQLite (→ Postgres si escala) · FastAPI · frontend React+TS+lightweight-charts · backtest propio.

## 📚 Documentos

- `docs/VISION.md` — qué, por qué, filosofía, copy-lead, go/no-go.
- `docs/RISK_MODEL.md` — matemática de riesgo, apalancamiento, sizing, stops.
- `docs/ARCHITECTURE.md` — estructura, módulos, funciones, datos, ops, resiliencia.
- `docs/ROADMAP.md` — fases con entregables (se construye una por sesión).
