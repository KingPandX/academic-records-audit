# Academic Records Audit

Sistema para auditar expedientes académicos en PDF:

1. **Convertir** todos los PDF de una carpeta a Markdown con [MarkItDown](https://github.com/microsoft/markitdown).
2. **Extraer** datos estructurados del Markdown hacia una base SQLite.

## Requisitos

- Python 3.10+
- Dependencias: `markitdown[pdf]`

## Instalación

```bash
cd academic-records-audit
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Uso rápido

1. Coloca los PDF en `data/pdfs/` (pueden estar en subcarpetas).
2. Ejecuta el pipeline completo:

```bash
academic-audit run
```

3. Revisa la base de datos:

```bash
sqlite3 data/audit.db "SELECT filename, status FROM documents;"
sqlite3 data/audit.db "SELECT full_name, student_id, program FROM students;"
sqlite3 data/audit.db "SELECT code, name, credits, grade FROM courses LIMIT 20;"
```

## Comandos

| Comando | Descripción |
|---------|-------------|
| `academic-audit run` | Convierte PDFs y extrae a SQLite |
| `academic-audit convert` | Solo PDF → Markdown |
| `academic-audit extract` | Solo Markdown → SQLite |
| `academic-audit init-db` | Crea el esquema vacío |
| `academic-audit run -v` | Modo verbose |

### Rutas personalizadas

```bash
academic-audit run \
  --pdf-dir /ruta/a/pdfs \
  --md-dir /ruta/a/markdown \
  --db /ruta/a/mi_auditoria.db
```

## Esquema SQLite (formato UNEFA)

- **documents** — cada PDF procesado
- **students** — apellidos, nombres, matrícula, documento de identidad, carrera, núcleo, índice académico final, fecha de emisión, etc.
- **courses** — periodo (`1-2022`), semestre (`01`), código, asignatura, calificación, U.C., puntos, observación (`REPITIÓ`, `APROBÓ`, …)
- **academic_index_snapshots** — índices académicos parciales del record (`23 UC`, `337 pts`, `IA 14.65`)
- **document_fields** — totales del resumen final (asignaturas cursadas/aprobadas, U.C., etc.)

El parser está calibrado con el record de referencia en `tests/fixtures/unefa_vasquez.md` (UNEFA, núcleo Miranda Santa Teresa).

### Consultas útiles

```bash
sqlite3 data/audit.db "
  SELECT surnames, given_names, student_id, identity_document, academic_index
  FROM students;
"

sqlite3 data/audit.db "
  SELECT c.document_id, d.filename, c.student_id, c.code, c.name, c.grade
  FROM courses c
  JOIN documents d ON d.id = c.document_id
  ORDER BY c.document_id, c.row_order;
"
```

Cada PDF genera un `document_id` distinto. Los cursos incluyen `student_id` (matrícula) para verificar la asignación sin joins.
```

## Estructura del proyecto

```
academic-records-audit/
├── data/
│   ├── pdfs/          # entrada
│   ├── markdown/      # salida MarkItDown
│   └── audit.db       # SQLite (generado)
└── src/academic_audit/
    ├── convert.py     # conversión PDF
    ├── extract.py     # carga a SQLite
    ├── parsers/       # heurísticas de extracción
    └── database.py    # esquema y persistencia
```

## Próximos pasos (auditoría)

- Reglas de validación (créditos mínimos, notas válidas, duplicados)
- Reportes de inconsistencias
- Comparación entre expediente y sistema oficial
