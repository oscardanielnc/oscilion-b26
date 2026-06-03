"""Shim de compatibilidad — la librería de estrategias vive ahora en
`oscilion.strategies.library` (ciudadano de primera clase). Mantener este
re-export para los scripts de research existentes.
"""
from oscilion.strategies.library import *  # noqa: F401,F403
from oscilion.strategies.library import REGISTRY, Ctx, TFArrays, aux_at  # noqa: F401
