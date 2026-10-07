# Análisis FODA - google-suite

**Fecha:** 2026-02-10  
**Analizado por:** Margarita (heartbeat de análisis de repos)

## 🔄 Revisión 2026-10-07 (después de los sprints 1–13)

El análisis original de abajo es de febrero (v0.1.2). Estado actual de lo que
señalaba:

| Punto del FODA | Estado |
|----------------|--------|
| Tests no ejecutables sin setup | ✅ Resuelto: `uv sync` + `uv run pytest`; ~1600 tests |
| Coverage no medida | ✅ Resuelto: combinado en CI, 87%, piso del 85% |
| Drive y Sheets básicos | ✅ Resuelto: Drive completo; Sheets con el motor de GSpreadManager |
| Docs de API REST limitadas | ⚠️ Parcial: sitio MkDocs con referencia; falta guía de deploy |
| Sin versionado semántico | ✅ Resuelto: release-please + conventional commits |
| Oportunidad: más APIs | ✅ Tasks y Contacts; Meet y Admin SDK pendientes |
| Oportunidad: async | ⚠️ Parcial: base + Sheets; Gmail/Calendar/Drive pendientes |
| Amenaza: cambios en Google APIs | Mitigada: nightly con dependencias latest y tests de integración opt-in |

| Métrica | Valor |
|---------|-------|
| **Madurez** | Beta (0.2.0 en preparación) |
| **Packages** | 7 (core, gmail, calendar, drive, sheets, tasks, contacts) |
| **Python** | 3.11–3.14 en CI (+ 3.15 experimental), Linux/macOS/Windows |
| **Seguridad** | gitleaks, pip-audit, CodeQL, Scorecard, actions pinneadas por SHA |
| **Docker** | 355 MB multi-stage (antes 525 MB) |

Nuevas debilidades:
- Las rutas de la API son síncronas y el rate limiting es solo del lado cliente.
- Los tests de integración dependen de un token OAuth que, con la app en modo
  "Testing", vence cada 7 días.

---

## 📊 Resumen Ejecutivo

**google-suite** es un SDK unificado de Python para Google Workspace APIs (Gmail, Calendar, Drive, Sheets) con arquitectura limpia. Publicado en PyPI como `gsuite-sdk`.

| Métrica | Valor |
|---------|-------|
| **Madurez** | Beta (v0.1.2) |
| **Stack** | Python 3.11+ |
| **Licencia** | MIT |
| **PyPI** | `gsuite-sdk` |
| **Packages** | 5 (core, gmail, calendar, drive, sheets) |
| **API REST** | ✅ FastAPI |
| **CLI** | ✅ Typer |
| **CI/CD** | ✅ GitHub Actions |

---

## 💪 Fortalezas (Strengths)

### 1. Arquitectura Unificada
- **Un solo OAuth flow** para acceder a Gmail, Calendar, Drive, Sheets
- Elimina la necesidad de configurar autenticación por separado para cada servicio
- Token storage centralizado (SQLite o Secret Manager)

### 2. Clean Architecture
- Separación clara: `packages/core`, `packages/gmail`, etc.
- Cada módulo puede usarse independientemente
- Interfaces bien definidas

### 3. Múltiples Interfaces
- **SDK Python**: Uso programático directo
- **REST API**: Gateway unificado con FastAPI (`/gmail/*`, `/calendar/*`, etc.)
- **CLI**: Comandos de terminal para operaciones comunes
- **AI Skill**: Compatible con OpenClaw agents

### 4. Publicado en PyPI
```bash
pip install gsuite-sdk
pip install gsuite-sdk[cloudrun]  # Con Secret Manager
pip install gsuite-sdk[all]       # Todas las dependencias
```

### 5. Documentación Completa
- README extenso con ejemplos
- Guía de credenciales
- Docstrings en código
- API docs auto-generadas

### 6. Query Builder para Gmail
```python
# Fluent API inspirada en simplegmail
messages = gmail.search(
    query.newer_than(days=7) & query.has_attachment()
)
```

---

## 😟 Debilidades (Weaknesses)

### 1. Tests No Ejecutables Sin Setup
- Los tests requieren `pip install -e .` previo
- Import errors si se corre pytest directamente
- **Impacto**: CI pasa pero desarrollador local puede confundirse

### 2. Coverage No Medida
- No hay badge de coverage en README
- No hay reports de coverage en CI
- Difícil saber qué partes están bien testeadas

### 3. Módulos con Diferente Nivel de Completitud
| Módulo | Estado |
|--------|--------|
| Gmail | ✅ Completo (443 líneas agregadas recientemente) |
| Calendar | ✅ Funcional |
| Core | ✅ Funcional |
| Drive | ⚠️ Básico |
| Sheets | ⚠️ Básico |

### 4. Documentación de API REST Limitada
- `/docs` funciona con Swagger
- Pero no hay guía de deploy a Cloud Run paso a paso

### 5. Sin Versionado Semántico Estricto
- v0.1.2 indica beta
- No hay CHANGELOG actualizado desde enero

---

## 🚀 Oportunidades (Opportunities)

### 1. Consolidación de Repos Standalone
Los repos `Gmail-API` y `Calendar-API` ya existen como deployments separados. Este SDK puede:
- Reemplazarlos eventualmente
- O consumirlos internamente

### 2. Expansión a Más APIs
- **Google Meet**: Crear/listar reuniones
- **Google Tasks**: Integración de tareas
- **Google Contacts**: Directorio de contactos
- **Admin SDK**: Para organizaciones

### 3. Integración con Proyectos Internos
- **clawd-workspace**: Ya usa Google Suite vía APIs separadas
- **CI-Slack-Bot**: Podría enviar emails vía este SDK
- **Twitter-to-Bigquery**: Notificaciones por Gmail

### 4. Plugin System
Permitir que terceros agreguen módulos para otras APIs Google.

### 5. Async Support
Actualmente es síncrono. Async mejoraría performance en batch operations.

---

## ⚠️ Amenazas (Threats)

### 1. Cambios en Google APIs
- Google depreca APIs sin mucho aviso
- Requiere mantenimiento continuo

### 2. Competencia con Librerías Establecidas
- `google-api-python-client` (oficial)
- `simplegmail` (3.5k stars)
- `gcsa` (Google Calendar Simple API)

**Diferenciador**: Ninguna ofrece SDK unificado con REST API y CLI.

### 3. Complejidad OAuth
- OAuth de Google requiere setup inicial
- Puede ser barrera de entrada para nuevos usuarios

### 4. Costos de Google Cloud
- Secret Manager tiene costos (mínimos pero existentes)
- Si el SDK gana tracción, podría ser problema para usuarios free-tier

---

## 📈 Métricas de Salud

| Aspecto | Estado | Notas |
|---------|--------|-------|
| README | ✅ Excelente | 346 líneas, ejemplos claros |
| CI | ✅ Funcional | GitHub Actions |
| Tests | ⚠️ Existen pero setup complejo | Import errors sin pip install -e |
| Coverage | ❌ No medida | Agregar pytest-cov a CI |
| Docstrings | ✅ Parcial | Core y Gmail bien, otros básicos |
| Últma actividad | ✅ Hoy | PR mergeado 2026-02-10 |

---

## 🎯 Recomendaciones Inmediatas

1. **Agregar coverage a CI** - Medir y mostrar badge
2. **Actualizar CHANGELOG** - Documentar cambios recientes
3. **Guía de deploy Cloud Run** - Paso a paso en docs/
4. **Completar Drive y Sheets** - Al nivel de Gmail/Calendar
5. **Fix tests locales** - Agregar script de setup o mejorar conftest.py

Ver [ROADMAP.md](./ROADMAP.md) para plan detallado.
