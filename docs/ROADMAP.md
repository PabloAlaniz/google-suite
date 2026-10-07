# Roadmap - google-suite

**Actualizado:** 2026-10-07  
**Basado en:** [Análisis FODA](./FODA.md)

## 🎯 Versión: 0.2.0 (próximo release)

Los sprints 1–13 (2026-10) cubrieron la estabilización y la expansión
planificadas para el primer semestre: CI dividida por paquete, gobernanza del
repo, endurecimiento de la API, resiliencia del core, Drive y Sheets
completos, el motor de GSpreadManager incorporado ([ADR 0001](adr/0001-incorporate-gspreadmanager.md)),
async (base + Sheets), Tasks, Contacts, sitio de docs, tests de integración e
imagen Docker más chica. 0.2.0 los publica.

---

## ✅ Estabilización (hecho)

- [x] **Tests ejecutables sin setup** - `uv sync` + `uv run pytest`; nombres de módulo únicos verificados
- [x] **Coverage en CI** - combinado entre paquetes, piso del 85%
- [x] **CHANGELOG** - automatizado con release-please (conventional commits)
- [x] **Drive completo** - share, trash/restore, copy, move, export, upload resumable; tests
- [x] **Sheets completo** - format, charts, pivots, add/del worksheet, protecciones, validaciones,
      formato condicional, upsert, modelos tipados, export (motor de GSpreadManager)
- [x] **CLI** - `drive upload`, `sheets read/write/export/import-csv/share`, `tasks`, `contacts`
- [x] **REST API**
  - [x] Request logging con X-Request-ID
  - [x] Errores RFC 9457 (problem+json)
  - [x] API key obligatoria por router (fail closed)
  - [ ] Rate limiting de la API (hoy solo hay token bucket del lado cliente: `GSUITE_RATE_LIMIT`)
- [x] **Sitio de documentación** - MkDocs + referencia de la API generada de los docstrings
- [x] **Tests de integración** - opt-in contra una cuenta real (`tests/integration`)
- [ ] **Documentación de deploy**
  - [ ] Guía paso a paso de Cloud Run (hoy hay una sección en `api/README.md`)
  - [ ] Docker compose
  - [ ] Troubleshooting

---

## 📍 Expansión

### Nuevos módulos

- [x] **Google Tasks** (`gsuite_tasks`, REST `/tasks`, CLI `gsuite tasks`)
  - [x] CRUD de tareas (subtareas, mover, completar/reabrir, filtros por vencimiento)
  - [x] Listas de tareas
  - [ ] Sync con Calendar

- [x] **Google Contacts** (`gsuite_contacts` sobre People API, REST `/contacts`, CLI `gsuite contacts`)
  - [x] Listar, buscar, crear, actualizar (con etag) y borrar
  - [ ] Grupos de contactos
  - [ ] Directorio de la organización (Workspace)

- [ ] **Google Meet**
  - [ ] Crear y listar reuniones
  - [ ] Links de grabaciones

### Performance

- [ ] **Async support** ([docs/ASYNC.md](./ASYNC.md))
  - [x] Base en `gsuite_core.aio` (httpx, reintentos y errores compartidos con sync)
  - [x] `AsyncSheets`
  - [ ] `AsyncGmail`, `AsyncCalendar`, `AsyncDrive`

- [ ] **Caching**
  - [x] Caché de lecturas de Sheets (`Sheets(auth, cache=True)`)
  - [ ] Caché de metadata de archivos de Drive

---

## 📍 Madurez

### Enterprise

- [ ] **Admin SDK** - usuarios, grupos, settings del dominio
- [ ] **Multi-cuenta** - varias cuentas, impersonation de service accounts, acceso delegado

### v1.0

- [ ] API freeze
- [ ] Guía de migración desde 0.x
- [ ] Soporte de largo plazo

---

## 📝 Notas

- **Owner**: Pablo Alaniz
- **Repo**: https://github.com/PabloAlaniz/google-suite
- **Docs**: https://pabloalaniz.github.io/google-suite/
- **PyPI**: https://pypi.org/project/gsuite-sdk/
- **License**: MIT
