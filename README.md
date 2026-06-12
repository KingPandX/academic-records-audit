# Academic Records Audit

Sistema para auditar expedientes académicos en PDF:

1. **Convertir** PDF a Markdown con [MarkItDown](https://github.com/microsoft/markitdown).
2. **Extraer** datos estructurados del Markdown hacia una base SQLite.
3. **Gestionar parámetros** persistentes del sistema.
4. **Importar planes de estudio** (pensum) con prelaciones desde archivos XLS.
5. **Generar reportes** de elegibilidad para inscripción (Art. 118 + prelaciones).

## Requisitos

- Python 3.10+
- Dependencias: `markitdown[pdf]`, `xlrd`

## Instalación

```bash
cd academic-records-audit
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Uso rápido

### 1. Pipeline completo (PDF → Markdown → SQLite)

Coloca los PDF en `data/pdfs/` y los comprobantes de inscripción en `data/inscripcion/`:

```bash
academic-audit run
```

Para persistir los datos en disco y generar reportes:

```bash
academic-audit run --db data/audit.db --report
```

### 2. Importar plan de estudio (pensum)

```bash
academic-audit plan import data/pensum.xls
academic-audit plan list
```

### 3. Configurar período actual

```bash
academic-audit param set periodo_actual "1-2025" --description "Período a evaluar"
```

### 4. Generar reporte de elegibilidad

```bash
academic-audit run --db data/audit.db --report
```

El reporte `reports/elegibilidad.csv` cruza los comprobantes de inscripción contra el historial académico y el plan de estudio, evaluando:

- **Prelaciones**: cada materia a inscribir se valida contra las prelaciones del pensum
- **Artículo 118**: 3 repitencias de una misma materia, >50% reprobadas en un período, TEG/prácticas reprobadas 2 períodos
- **Resultado**: APTO / NO APTO con observaciones detalladas

## Comandos

| Comando | Descripción |
|---------|-------------|
| `academic-audit run` | Pipeline completo: convertir y extraer |
| `academic-audit convert` | Solo PDF → Markdown |
| `academic-audit extract` | Solo Markdown → SQLite |
| `academic-audit init-db` | Crea el esquema vacío |
| `academic-audit plan import <file.xls>` | Importar plan de estudio |
| `academic-audit plan list` | Listar programas importados |
| `academic-audit param set <key> <value>` | Guardar parámetro persistente |
| `academic-audit param get <key>` | Obtener valor de parámetro |
| `academic-audit param list` | Listar todos los parámetros |
| `academic-audit param delete <key>` | Eliminar un parámetro |

### Opciones comunes

| Opción | Descripción |
|--------|-------------|
| `--db <path>` | Ruta a la base SQLite (por defecto: en memoria) |
| `--pdf-dir <path>` | Carpeta con PDFs de expedientes |
| `--md-dir <path>` | Carpeta de salida Markdown |
| `--inscripcion-dir <path>` | Carpeta con PDFs de inscripción |
| `--inscripcion-md-dir <path>` | Carpeta de salida Markdown de inscripción |
| `--report` | Generar reportes CSV al finalizar |
| `--report-dir <path>` | Directorio de salida para reportes |
| `--workers <n>` | Hilos paralelos para conversión (default: 3) |
| `-v` / `--verbose` | Salida detallada |

### Rutas personalizadas

```bash
academic-audit run \
  --pdf-dir /ruta/a/pdfs \
  --md-dir /ruta/a/markdown \
  --inscripcion-dir /ruta/a/inscripcion \
  --db /ruta/a/mi_auditoria.db
```

## Reportes

### estudiantes-materias.csv

Listado completo de todas las materias cursadas por todos los estudiantes, ordenado por matrícula y período.

### elegibilidad.csv

Evaluación de elegibilidad para inscripción. Por cada estudiante:

| Columna | Descripción |
|---------|-------------|
| `identity_document` | Cédula de identidad |
| `full_name` | Nombre completo |
| `program` | Carrera |
| `periodo_actual` | Período a inscribir |
| `indice_academico` | Índice académico |
| `materias_a_inscribir` | Materias del comprobante de inscripción |
| `prelaciones_incumplidas` | Prelaciones que faltan por materia |
| `violaciones_art118` | Causales del Artículo 118 detectadas |
| `elegibilidad` | APTO / NO APTO |

## Parámetros persistentes

Los parámetros se almacenan en `~/.config/academic-audit/parameters.db` (o `$XDG_CONFIG_HOME/academic-audit/parameters.db`) y persisten entre ejecuciones independientemente del modo memoria.

Parámetros del sistema:

| Clave | Descripción | Ejemplo |
|-------|-------------|---------|
| `periodo_actual` | Período académico vigente para evaluar elegibilidad | `1-2025` |

## Plan de estudio (pensum)

El sistema importa planes de estudio desde archivos XLS (formato UNEFA). Cada hoja del XLS representa un programa con sus materias, créditos, semestre y prelaciones.

Las prelaciones se evalúan automáticamente al generar el reporte de elegibilidad: cada materia del comprobante de inscripción se valida contra el historial académico del estudiante.

## Esquema SQLite

### Base de datos principal (efímera / `--db`)

- **documents** — cada PDF procesado
- **students** — apellidos, nombres, matrícula, documento de identidad, carrera, núcleo, índice académico, fecha de emisión
- **courses** — período (`1-2022`), semestre (`01`), código, asignatura, calificación, U.C., puntos, observación (`REPITIÓ`, `APROBÓ`, …)
- **academic_index_snapshots** — índices académicos parciales
- **document_fields** — totales del resumen final
- **enrollments** — comprobantes de inscripción
- **enrollment_subjects** — materias inscritas por período

### Base de parámetros (persistente)

Ubicada en `~/.config/academic-audit/parameters.db`:

- **parameters** — clave → valor
- **plan_subjects** — materias del pensum por programa
- **plan_prerequisites** — prelaciones entre materias

## Resolución de documentos

Cada archivo PDF se vincula con su Markdown mediante el nombre base (`N-30162461.pdf` ↔ `N-30162461.md`). El pipeline usa `document_resolver.py` para hacer este matching automáticamente.

## Estructura del proyecto

```
academic-records-audit/
├── data/
│   ├── pdfs/                 # Entrada: expedientes PDF
│   ├── markdown/             # Salida: Markdown de expedientes
│   ├── inscripcion/          # Entrada: comprobantes de inscripción PDF
│   ├── markdown-inscripcion/ # Salida: Markdown de inscripciones
│   └── audit.db              # SQLite (generado con --db)
├── reports/                  # Reportes CSV generados
└── src/academic_audit/
    ├── cli.py                # Interfaz de línea de comandos
    ├── config.py             # Configuración y rutas
    ├── database.py           # Esquema SQLite y clase Database
    ├── study_plan.py         # Parser de planes de estudio (XLS)
    ├── eligibility.py        # Motor de reglas de elegibilidad
    ├── report.py             # Generación de reportes CSV
    ├── convert.py            # Conversión PDF → Markdown (expedientes)
    ├── extract.py            # Extracción Markdown → SQLite (expedientes)
    ├── convert_inscripcion.py# Conversión PDF → Markdown (inscripciones)
    ├── extract_inscripcion.py# Extracción Markdown → SQLite (inscripciones)
    ├── pipeline.py           # Orquestador del pipeline completo
    ├── document_resolver.py  # Vinculación PDF ↔ Markdown
    └── parsers/
        ├── unefa.py          # Parser de transcriptos UNEFA
        ├── inscripcion.py    # Parser de comprobantes de inscripción
        └── transcript.py     # Parser genérico de transcriptos
```
