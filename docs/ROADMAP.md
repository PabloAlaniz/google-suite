# Roadmap - google-suite

**Actualizado:** 2026-02-10  
**Basado en:** [Análisis FODA](./FODA.md)

## 🎯 Versión Actual: 0.1.2 (Beta)

---

## 📍 Q1 2026 - Estabilización

### P0 - Crítico (Esta semana)

- [ ] **Fix test imports** - Agregar `pip install -e .` a conftest.py o documentar setup
- [ ] **Agregar coverage a CI** - pytest-cov + badge en README
- [ ] **Actualizar CHANGELOG.md** - Documentar Gmail API expansion (PR #1)

### P1 - Alta (Este mes)

- [ ] **Completar Drive module**
  - [ ] `drive.share()` - Compartir archivos
  - [ ] `drive.trash()` / `drive.restore()` - Papelera
  - [ ] `drive.copy()` - Copiar archivos
  - [ ] `drive.move()` - Mover entre carpetas
  - [ ] Tests para todas las operaciones

- [ ] **Completar Sheets module**
  - [ ] `sheets.format()` - Formateo de celdas
  - [ ] `sheets.create_chart()` - Gráficos
  - [ ] `sheets.add_sheet()` / `sheets.delete_sheet()` - Gestión de hojas
  - [ ] `sheets.protect()` - Protección de rangos
  - [ ] Tests completos

- [ ] **Documentación de deploy**
  - [ ] `docs/DEPLOY_CLOUD_RUN.md` - Guía paso a paso
  - [ ] `docs/DEPLOY_DOCKER.md` - Docker compose
  - [ ] `docs/TROUBLESHOOTING.md` - Problemas comunes

### P2 - Media (Q1)

- [ ] **CLI improvements**
  - [ ] `gsuite drive upload <file>` - Upload desde CLI
  - [ ] `gsuite sheets read <id> <range>` - Leer sheets
  - [ ] `gsuite sheets write <id> <range> <data>` - Escribir

- [ ] **REST API improvements**
  - [ ] Rate limiting middleware
  - [ ] Request logging
  - [ ] Better error responses (RFC 7807)

---

## 📍 Q2 2026 - Expansión

### Nuevos Módulos

- [ ] **Google Meet**
  - [ ] Crear reuniones
  - [ ] Listar reuniones
  - [ ] Obtener recording links
  - [ ] Integracion con Calendar

- [ ] **Google Tasks**
  - [ ] CRUD de tareas
  - [ ] Listas de tareas
  - [ ] Sync con Calendar

### Performance

- [ ] **Async support**
  - [ ] `AsyncGmail`, `AsyncDrive`, etc.
  - [ ] Batch operations optimizadas
  - [ ] Connection pooling

- [ ] **Caching**
  - [ ] Cache de tokens mejorado
  - [ ] Cache de metadata de archivos
  - [ ] Invalidación inteligente

---

## 📍 Q3-Q4 2026 - Madurez

### Enterprise Features

- [ ] **Admin SDK**
  - [ ] User management
  - [ ] Group management
  - [ ] Domain settings

- [ ] **Multi-tenant**
  - [ ] Soporte para múltiples cuentas
  - [ ] Service account impersonation
  - [ ] Delegated access

### Plugin System

- [ ] **Extensibilidad**
  - [ ] Plugin discovery
  - [ ] Custom module registration
  - [ ] Third-party integrations

### v1.0 Release

- [ ] **Estabilidad garantizada**
  - [ ] API freeze
  - [ ] Migration guide desde 0.x
  - [ ] Long-term support

---

## 📊 Tareas Extraídas para Mission Control

Las siguientes tareas serán creadas en Mission Control:

| ID | Título | Prioridad | Asignado |
|----|--------|-----------|----------|
| - | Fix test imports en google-suite | HIGH | houdini |
| - | Agregar coverage a CI en google-suite | HIGH | marikondo |
| - | Actualizar CHANGELOG.md de google-suite | MEDIUM | cortazar |
| - | Completar Drive module | MEDIUM | alex |
| - | Completar Sheets module | MEDIUM | alex |
| - | Docs: Deploy Cloud Run para google-suite | MEDIUM | cortazar |

---

## 📝 Notas

- **Owner**: Pablo Alaniz
- **Repo**: https://github.com/PabloAlaniz/google-suite
- **PyPI**: https://pypi.org/project/gsuite-sdk/
- **License**: MIT

Este roadmap se revisa mensualmente. Última revisión: 2026-02-10.
