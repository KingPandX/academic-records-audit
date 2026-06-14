# Academic Records Audit — Documentación Técnica para Tesis

## 1. Descripción General

**Academic Records Audit** es un sistema de procesamiento, análisis y consulta de expedientes académicos universitarios. Está diseñado para instituciones que emiten registros de calificaciones en formato PDF (como la UNEFA — Universidad Nacional Experimental Politécnica de la Fuerza Armada Nacional Bolivariana).

### 1.1 Propósito

El sistema automatiza el flujo de trabajo que va desde la recepción de expedientes académicos en PDF hasta la generación de reportes de elegibilidad, estadísticas de rendimiento y consultas inteligentes sobre los datos estudiantiles. Permite clasificar a los estudiantes en categorías académicas (regular, repitiente, desfasado), evaluar su elegibilidad según el Artículo 118, y visualizar la información mediante una interfaz web interactiva.

### 1.2 Funcionalidades Principales

- Conversión de PDFs de expedientes académicos a Markdown estructurado
- Extracción de datos estructurados (estudiantes, cursos, calificaciones) hacia una base de datos SQLite
- Procesamiento de certificados de inscripción (PDF → Markdown → SQLite)
- Importación de planes de estudio (pensum) desde archivos XLS
- Evaluación de elegibilidad estudiantil (Artículo 118)
- Clasificación de estudiantes: regular, repitiente, desfasado
- Generación de reportes en formato CSV
- Consultas en lenguaje natural mediante IA (Groq)
- Interfaz web (FastAPI + Jinja2) e interfaz alternativa (Gradio)

---

## 2. Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            USUARIO                                          │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
            ┌───────────────────┼───────────────────┐
            ▼                   ▼                   ▼
    ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
    │   FastAPI     │   │    Gradio     │   │      CLI      │
    │  (Web UI)     │   │  (Alterna.)   │   │  (Terminal)   │
    └───────┬───────┘   └───────┬───────┘   └───────┬───────┘
            │                   │                   │
            └───────────────────┼───────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │   Capa de Lógica     │
                    │   (Módulos Python)   │
                    └───────────┬───────────┘
                                │
          ┌─────────────────────┼──────────────────────┐
          ▼                     ▼                      ▼
  ┌──────────────┐    ┌────────────────┐    ┌──────────────────┐
  │  Base de     │    │  Base de       │    │    Archivos      │
  │  Datos       │    │  Parámetros    │    │   (PDF, MD, CSV) │
  │  (audit.db)  │    │  (parameters   │    │                  │
  │              │    │   .db)         │    │                  │
  └──────────────┘    └────────────────┘    └──────────────────┘
```

### 2.1 Componentes del Sistema

| Componente | Tecnología | Propósito |
|---|---|---|
| **Web UI** | FastAPI + Jinja2 + CSS | Interfaz principal con tabs interactivos |
| **GUI Alternativa** | Gradio | Versión simplificada para escritorio |
| **CLI** | argparse | Automatización por terminal |
| **Base Principal** | SQLite (`audit.db`) | Datos de estudiantes, cursos, inscripciones |
| **Base de Parámetros** | SQLite (`parameters.db`) | Planes de estudio, parámetros del sistema |
| **Parser UNEFA** | Python (regex) | Extrae datos de transcripts UNEFA |
| **Parser Inscripciones** | Python (regex) | Extrae datos de certificados de inscripción |
| **Parser Pensum** | xlrd | Importa plan de estudios desde .xls |
| **Motor de Elegibilidad** | Python | Evalúa Art. 118 y prelaciones |
| **Clasificador** | Python | Clasifica estudiantes en categorías |
| **Motor de Consultas IA** | Groq API | Consultas en lenguaje natural |

### 2.2 Flujo de Datos del Pipeline Principal

```
PDFs (transcripts)                 PDFs (inscripciones)
       │                                   │
       ▼                                   ▼
┌──────────────┐                  ┌──────────────────┐
│  convert.py  │                  │convert_inscripcion│
│  PDF → MD    │                  │    .py PDF → MD  │
└──────┬───────┘                  └────────┬─────────┘
       │                                   │
       ▼                                   ▼
┌──────────────┐                  ┌──────────────────┐
│  extract.py  │                  │extract_inscripcion│
│  MD → SQLite │                  │   .py MD→SQLite  │
└──────┬───────┘                  └────────┬─────────┘
       │                                   │
       └───────────────┬───────────────────┘
                       ▼
              ┌────────────────┐
              │   audit.db    │
              │   (SQLite)    │
              └───────┬────────┘
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
  ┌────────────┐ ┌────────┐ ┌──────────┐
  │  Reportes  │ │Elegib. │ │Consultas │
  │  CSV       │ │Art.118 │ │   IA     │
  └────────────┘ └────────┘ └──────────┘
```

---

## 3. Estructura del Proyecto

```
academic-records-audit/
│
├── pyproject.toml                  # Configuración del proyecto (dependencias, build)
├── THESIS_DOCUMENTATION.md         # ← Este documento
├── README.md
│
├── src/
│   └── academic_audit/             # Paquete principal
│       │
│       ├── __init__.py             # Versión (0.1.0)
│       ├── config.py               # Rutas, patrones de extracción, dataclasses
│       ├── database.py             # Esquema SQLite + clase Database (CRUD)
│       ├── pipeline.py             # Orquestador del pipeline completo
│       ├── cli.py                  # Interfaz de línea de comandos (argparse)
│       │
│       ├── convert.py              # Conversión PDF → Markdown (transcripts)
│       ├── convert_inscripcion.py  # Conversión PDF → Markdown (inscripciones)
│       ├── extract.py              # Extracción Markdown → SQLite (transcripts)
│       ├── extract_inscripcion.py  # Extracción Markdown → SQLite (inscripciones)
│       │
│       ├── parsers/
│       │   ├── transcript.py       # Parser genérico de transcripts
│       │   ├── unefa.py            # Parser específico UNEFA
│       │   └── inscripcion.py      # Parser de inscripciones
│       │
│       ├── document_resolver.py    # Vinculación PDF ↔ Markdown
│       ├── study_plan.py           # Importación de plan de estudios (.xls)
│       ├── eligibility.py          # Motor de elegibilidad (Artículo 118)
│       ├── student_stats.py        # Clasificación de estudiantes
│       ├── report.py               # Generación de reportes CSV
│       ├── query.py                # Consultas en lenguaje natural (IA)
│       │
│       └── web/
│           ├── __init__.py
│           ├── app.py              # Aplicación FastAPI (rutas, endpoints)
│           ├── tasks.py            # Gestor de tareas asíncronas (SSE)
│           ├── static/
│           │   ├── style.css       # Estilos (tema oscuro)
│           │   ├── app.js          # Lógica del frontend
│           │   └── reports/        # Copias estáticas de reportes CSV
│           └── templates/
│               ├── index.html      # SPA principal
│               └── tabs/           # Vistas parciales por pestaña
│                   ├── pipeline.html
│                   ├── study_plan.html
│                   ├── parameters.html
│                   ├── eligibility.html
│                   ├── reports.html
│                   └── query.html
│
├── tests/                          # Suite de pruebas
│   ├── __init__.py
│   ├── conftest.py                 # Fixtures compartidas
│   ├── test_document_resolver.py
│   ├── test_eligibility.py         # 21 tests (Art.118, prelaciones)
│   ├── test_student_stats.py       # 8 tests (clasificación)
│   ├── test_unefa_parser.py        # 12 tests (parser)
│   ├── test_report.py             # 7 tests (reportes CSV)
│   ├── sample_transcript.md        # Transcript de prueba genérico
│   └── fixtures/
│       └── unefa_vasquez.md        # Transcript UNEFA real (136 líneas)
│
├── data/                           # Datos de ejecución
│   ├── audit.db                    # Base de datos SQLite principal
│   ├── pdfs/                       # PDFs fuente de transcripts
│   ├── markdown/                   # Markdowns convertidos
│   ├── inscripcion/                # PDFs de inscripciones
│   ├── markdown-inscripcion/       # Markdowns de inscripciones
│   └── pensum.xls                  # Plan de estudios fuente
│
└── reports/                        # Reportes CSV generados
    ├── estudiantes-materias.csv
    ├── elegibilidad.csv
    └── estadisticas-carreras.csv
```

---

## 4. Base de Datos

El sistema utiliza **dos bases de datos SQLite** separadas:

### 4.1 Base de Datos Principal (`audit.db`)

Almacena los datos extraídos de los expedientes académicos y certificados de inscripción.

```
┌───────────────────────────────────────────────────────────────────────┐
│                     ESQUEMA ENTIDAD-RELACIÓN                        │
│                                                                      │
│  ┌──────────────┐       ┌──────────────────┐                        │
│  │  documents   │       │    students      │                        │
│  ├──────────────┤       ├──────────────────┤                        │
│  │ PK id        │◄──────┤ FK document_id   │ (1:1)                  │
│  │    source_pdf│       │    full_name     │                        │
│  │    markdown  │       │    student_id    │                        │
│  │    _path     │       │    identity_doc  │                        │
│  │    filename  │       │    program       │                        │
│  │    content   │       │    study_plan    │                        │
│  │    _hash     │       │    _period       │                        │
│  │    status    │       │    periods_comp  │                        │
│  │    error_msg │       │    nucleus       │                        │
│  │    processed │       │    academic_idx  │                        │
│  │    _at       │       │    issue_date    │                        │
│  └──────┬───────┘       │    faculty       │                        │
│         │               │    gpa           │                        │
│         │               └──────────────────┘                        │
│         │                                                           │
│         │ 1:N                  1:N                                  │
│         ▼                      ▼                                    │
│  ┌──────────────┐       ┌──────────────────┐                        │
│  │   courses    │       │  document_fields  │                        │
│  ├──────────────┤       ├──────────────────┤                        │
│  │ FK document  │       │ FK document_id   │                        │
│  │    _id       │       │    field_key     │                        │
│  │    student_id│       │    field_value   │                        │
│  │    period    │       └──────────────────┘                        │
│  │    semester  │                                                   │
│  │    code      │       ┌──────────────────────────┐                │
│  │    name      │       │ academic_index_snapshots  │                │
│  │    grade     │       ├──────────────────────────┤                │
│  │    credits   │       │ FK document_id           │                │
│  │    points    │       │    uc_cumulative         │                │
│  │    observ.   │       │    points_cumulative     │                │
│  │    course_typ│       │    index_value           │                │
│  │    year      │       └──────────────────────────┘                │
│  │    row_order │                                                   │
│  │    source_ln │       ┌──────────────────┐                        │
│  │    identity_ │       │   enrollments    │                        │
│  │    document  │       ├──────────────────┤                        │
│  └──────────────┘       │ PK id            │                        │
│                         │    source_pdf    │                        │
│  ┌──────────────────────┤    identity_doc  │                        │
│  │ enrollment_subjects  │    full_name     │                        │
│  ├──────────────────────┤    period        │                        │
│  │ FK enrollment_id     │    program       │                        │
│  │    code              │    status        │                        │
│  │    name              └────────┬─────────┘                        │
│  │    section                   │                                  │
│  │    teacher                   │ 1:N                              │
│  │    row_order                 ▼                                  │
│  └──────────────────────┐┌──────────────────┐                      │
│                        ││enroll_subjects   │                      │
│                        │└──────────────────┘                      │
└───────────────────────────────────────────────────────────────────────┘
```

#### Tablas

| Tabla | Descripción | Columnas Clave |
|---|---|---|
| **documents** | Registro de cada PDF procesado | `source_pdf` (único), `status` (pending/converted/extracted/failed), `markdown_path` |
| **students** | Datos demográficos y académicos del estudiante | `identity_document` (único), `program`, `periods_completed`, `academic_index` |
| **courses** | Historial de materias cursadas | `period` (ej. "1-2023"), `semester` (ej. "01"), `code`, `grade`, `credits`, `observation` (APROBÓ/REPROBÓ/REPITIÓ) |
| **document_fields** | Metadatos adicionales del transcript | `field_key`/`field_value` (total cursos cursados/aprobados, UC, etc.) |
| **academic_index_snapshots** | Instantáneas del índice académico por período | `uc_cumulative`, `points_cumulative`, `index_value` |
| **enrollments** | Certificados de inscripción procesados | `identity_document` (único), `period`, `program` |
| **enrollment_subjects** | Materias inscritas en un período | `code`, `name`, `section`, `teacher` |

#### Relaciones

```
documents.id ──1:1──→ students.document_id
documents.id ──1:N──→ courses.document_id
documents.id ──1:N──→ document_fields.document_id
documents.id ──1:N──→ academic_index_snapshots.document_id
students.identity_document ──1:N──→ courses.identity_document
enrollments.id ──1:N──→ enrollment_subjects.enrollment_id
```

### 4.2 Base de Datos de Parámetros (`parameters.db`)

Almacena la configuración del sistema y los planes de estudio (pensum). Se encuentra en `~/.config/academic-audit/parameters.db`.

```
┌──────────────────────────────────────────────────┐
│              PARÁMETROS (parameters.db)          │
│                                                  │
│  ┌──────────────────┐   ┌────────────────────┐   │
│  │   parameters     │   │   plan_subjects    │   │
│  ├──────────────────┤   ├────────────────────┤   │
│  │ PK key           │   │ PK code            │   │
│  │    value         │   │ PK program         │   │
│  │    description   │   │    name            │   │
│  │    updated_at    │   │    credits         │   │
│  └──────────────────┘   │    semester        │   │
│                         │    subject_type    │   │
│  ┌────────────────────────────┐              │   │
│  │   plan_prerequisites       │              │   │
│  ├────────────────────────────┤              │   │
│  │ PK subject_code            │              │   │
│  │ PK prereq_code             │              │   │
│  │ PK program                 │              │   │
│  └────────────────────────────┘              │   │
└──────────────────────────────────────────────────┘
```

| Tabla | Descripción | Columnas Clave |
|---|---|---|
| **parameters** | Parámetros del sistema | `key` (PK, ej. "periodo_actual", "groq_api_key"), `value` |
| **plan_subjects** | Materias del plan de estudios por programa | `code` + `program` (PK), `semester` (número del 1 al 10), `credits`, `subject_type` (obligatoria, teg, practica) |
| **plan_prerequisites** | Prelaciones entre materias | `subject_code` + `prereq_code` + `program` (PK) |

#### Relaciones entre Parámetros y Plan de Estudios

```
plan_subjects.code ──1:N──→ plan_prerequisites.subject_code
plan_subjects.code ──1:N──→ plan_prerequisites.prereq_code
```

---

## 5. Módulos del Sistema

### 5.1 Configuración (`config.py`)

Define las rutas por defecto del sistema y las configuraciones de extracción.

```
Paths:
  pdf_dir              → data/pdfs/
  markdown_dir         → data/markdown/
  inscripcion_dir      → data/inscripcion/
  inscripcion_md_dir   → data/markdown-inscripcion/
  db_path              → data/audit.db
  report_dir           → reports/
```

### 5.2 Pipeline de Procesamiento

El pipeline es el flujo central de datos. Se ejecuta desde la CLI (`academic-audit run`) o desde la interfaz web.

```
┌──────────────────────────────────────────────────────────────────┐
│                        PIPELINE COMPLETO                        │
│                                                                  │
│  1. CONVERTIR PDF → MARKDOWN                                     │
│     ├── convert_folder(pdf_dir, md_dir)                          │
│     │   ├── Por cada PDF:                                        │
│     │   │   ├── markitdown → Markdown estructurado               │
│     │   │   └── database.upsert_document(status="converted")    │
│     │   └── [Paralelo con N workers]                             │
│     │                                                            │
│  2. EXTRAER MARKDOWN → SQLITE                                    │
│     ├── extract_folder(md_dir)                                   │
│     │   ├── Por cada .md:                                        │
│     │   │   ├── UnefaTranscriptParser.parse(markdown)            │
│     │   │   └── database.save_extraction(student, courses)       │
│     │   │                                                        │
│  3. CONVERTIR INSCRIPCIONES PDF → MARKDOWN                       │
│     └── convert_inscripcion_folder(insc_dir, insc_md_dir)        │
│                                                                  │
│  4. EXTRAER INSCRIPCIONES MARKDOWN → SQLITE                      │
│     └── extract_inscripcion_folder(insc_md_dir)                  │
│         └── database.save_enrollment(student, subjects)          │
│                                                                  │
│  5. GENERAR REPORTES (opcional)                                  │
│     └── generate_reports() → CSV files                           │
└──────────────────────────────────────────────────────────────────┘
```

### 5.3 Parser UNEFA (`parsers/unefa.py`)

Es el módulo más complejo del sistema. Procesa el formato de transcript emitido por la UNEFA.

```
┌──────────────────────────────────────────────────────────────────┐
│                   ESTRUCTURA DEL PARSER UNEFA                  │
│                                                                  │
│  Entrada: Texto Markdown (convertido desde PDF)                  │
│                                                                  │
│  UnefaTranscriptParser.parse(markdown)                           │
│    │                                                             │
│    ├── _extract_student()                                        │
│    │   ├── Apellidos + Matrícula (regex)                        │
│    │   ├── Nombres + Período Plan Estudio (regex)               │
│    │   ├── Documento Identidad + Períodos Cursados (regex)      │
│    │   ├── Carrera, Núcleo, Índice (regex)                      │
│    │   └── Totales (cursadas, aprobadas, UC)                    │
│    │                                                             │
│    ├── _extract_index_snapshots()                                │
│    │   └── Líneas con "Índice Académico" → {UC, Puntos, IA}    │
│    │                                                             │
│    └── _extract_courses()                                        │
│        ├── _parse_cinu() → Cursos CINU (formato especial)       │
│        └── _parse_course_line() → Cursos regulares              │
│            ├── Líneas con formato:                               │
│            │   <period> <sem> <code> <name> <grade> <cred> <pts>│
│            ├── Líneas en tabla pipe:                             │
│            │   | <period> <sem> | <code> <name> | <grade> ... | │
│            └── Líneas con APROBÓ/REPROBÓ en línea siguiente     │
│                                                                  │
│  Salida: ParsedTranscript(student, courses, snapshots, fields)  │
└──────────────────────────────────────────────────────────────────┘
```

#### Formato de Entrada (Markdown)

```
Apellidos: VASQUEZ ABREU Matricula: 1-2021-30255692
Nombres: JOSUÉ GABRIEL Período Académico según Plan de Estudio: 9
Documento de Identidad: V-30255692  Período Académico Cursados: 8
Carrera: INGENIERÍA DE SISTEMAS
1-2021 CINU2011 Curso Integral de Nivelación Universitario (CINU) REPROBÓ
2-2021 CINU2011 Curso Integral de Nivelación Universitario (CINU) APROBÓ
Período Sem Código Asignatura Calif.    U.C    Puntos Observación
1-2022 01  DIN-21113 DEFENSA INTEGRAL DE LA NACIÓN I 19      3      57
| 1-2022 01  | MAT-21212 DIBUJO              | 11      2      22 |     |
...
Índice académico: 14.54
Total asignaturas cursadas: 67  Total asignaturas aprobadas: 65
```

### 5.4 Motor de Elegibilidad (`eligibility.py`)

Evalúa si un estudiante cumple con los requisitos del **Artículo 118** del Reglamento de la UNEFA.

```
┌──────────────────────────────────────────────────────────────────┐
│                    EVALUACIÓN DE ELEGIBILIDAD                    │
│                                                                  │
│  evaluate_student(db, identity, current_period)                  │
│    │                                                             │
│    ├── 1. Obtener información del estudiante                     │
│    │    └── get_student_info()                                   │
│    │                                                             │
│    ├── 2. Obtener historial de cursos                           │
│    │    └── get_student_courses()                                │
│    │                                                             │
│    ├── 3. Verificar Artículo 118                                │
│    │    ├── check_article_118a(): 3+ reprobadas misma materia   │
│    │    ├── check_article_118b(): >50% reprobadas en un período │
│    │    └── check_article_118c(): TEG/Pasantía 2+ períodos     │
│    │                                                             │
│    ├── 4. Obtener inscripción actual                            │
│    │    └── enrollment_subjects                                  │
│    │                                                             │
│    └── 5. Verificar prelaciones                                 │
│         └── check_prerequisites() por cada materia               │
│             └── Usa plan_prerequisites de la BD de parámetros   │
│                                                                  │
│  Resultado: APTO / NO APTO + violaciones + prelaciones          │
└──────────────────────────────────────────────────────────────────┘
```

#### Artículo 118 — Causales de NO APTO

| Literal | Descripción | Condición |
|---|---|---|
| **a** | Reprobación de una misma asignatura 3 o más veces | `count(reprobadas) >= 3` por código |
| **b** | Reprobación de más del 50% de las asignaturas inscritas en un período | `failed / total > 0.5` por período |
| **c** | Reprobación del Trabajo Especial de Grado o Prácticas Profesionales en 2 períodos distintos | `count(distinct period) >= 2` para códigos TEG/Pasantía |

### 5.5 Clasificador de Estudiantes (`student_stats.py`)

Clasifica a los estudiantes según su avance académico relativo al plan de estudios, usando dos criterios: (1) retraso respecto al cohorte de ingreso, y (2) repitencia de materias previamente reprobadas.

```
┌──────────────────────────────────────────────────────────────────┐
│                   CLASIFICACIÓN DE ESTUDIANTES                  │
│                                                                  │
│  Entrada: identity_document + período actual                     │
│                                                                  │
│  classify_student(db, identity, current_period)                  │
│    │                                                             │
│    ├── 1. Obtener semestre_esperado                              │
│    │    └── study_plan_period (según cohorte/corte de ingreso)   │
│    │        ↓ fallback: periods_completed                        │
│    │        (0 = CINU, 1 = Semestre I, ..., 10 = Semestre X)    │
│    │                                                             │
│    ├── 2. Obtener materias actuales                             │
│    │    ├── enrollment_subjects (primera opción)                │
│    │    └── courses del último período (fallback)               │
│    │                                                             │
│    ├── 3. Mapear materias a semestres del plan                   │
│    │    └── plan_subjects(code → semester)                      │
│    │                                                             │
│    ├── 4. Determinar semestre_efectivo = max(semesters)         │
│    │                                                             │
│    ├── 5. Verificar repitencia                                   │
│    │    └── _check_repeated_failed(): ¿alguna materia inscrita   │
│    │        fue reprobada previamente (grade < 10 o REPROBÓ)?   │
│    │                                                             │
│    └── 6. Clasificar (jerarquía estricta):                      │
│         ┌── sem_efectivo < sem_esperado ─────────────────────┐   │
│         │                      →  DESFASADO                  │   │
│         │   (retrasado respecto a su cohorte de ingreso)     │   │
│         ├── materia inscrita reprobada previamente ──────┐   │   │
│         │                      →  REPITIENTE             │   │   │
│         │   (está repitiendo una materia que ya falló)   │   │   │
│         └── ninguna anterior ──────────────────────────┐   │   │
│                            →  REGULAR                  │   │   │
│                                                         │   │   │
└──────────────────────────────────────────────────────────────────┘
```

#### Categorías

| Categoría | Definición | Prioridad |
|---|---|---|
| **Desfasado** | Estudiante que no se gradúa con sus compañeros porque está al menos un semestre atrasado según su cohorte de ingreso (`study_plan_period`). Su semestre efectivo es menor al esperado. | 1 (máxima) |
| **Repitiente** | Estudiante que en su carga académica actual tiene inscrita al menos una materia que ya cursó y reprobó en su récord académico. | 2 |
| **Regular** | Estudiante que no está retrasado respecto a su cohorte y no está repitiendo materias reprobadas. | 3 |

**Nota**: La jerarquía asegura que un estudiante retrasado que además esté repitiendo materias se clasifique como **Desfasado** (la condición más grave prevalece).

#### Flujo de `_check_repeated_failed()`

```
_check_repeated_failed(db, identity_document, enrolled_subjects)
  │
  ├── Extraer códigos de materias inscritas
  ├── Consultar courses WHERE identity_document = ?
  ├── Para cada course cuyo código coincida:
  │   └── ¿_is_failed(grade, observation)?
  │       ├── grade < 10 o grade/obs = "REPROBÓ" → True
  │       └── caso contrario → False
  └── Retornar True si alguna materia reprobada está siendo repetida
```

#### Generación de Reporte Pivot

```
compute_stats_pivot(db, current_period)
  │
  ├── Clasificar todos los estudiantes
  ├── Agrupar por (programa, clasificación)
  ├── Para cada grupo, contar por semestre_efectivo (I a X)
  └── Retornar filas: Carrera | Tipo | I | II | III | ... | X
```

**Ejemplo de salida:**
```csv
Carrera,Tipo,I,II,III,IV,V,VI,VII,VIII,IX,X
INGENIERÍA DE SISTEMAS,Regular,0,0,0,0,0,1,0,0,0,0
INGENIERÍA DE SISTEMAS,Repitiente,23,25,0,0,0,0,0,0,0,0
INGENIERÍA DE SISTEMAS,Desfasado,0,0,0,0,0,0,0,0,0,0
```

### 5.6 Generación de Reportes (`report.py`)

Arquitectura basada en el patrón **Template Method** a través de una clase base abstracta.

```
┌──────────────────────────────────────────────────────────────────┐
│                   SISTEMA DE REPORTES (CSV)                     │
│                                                                  │
│  ReportWriter (ABC)                                              │
│  ├── filename: str (abstracto)                                   │
│  ├── columns: list[str] (abstracto)                              │
│  ├── label: str (etiqueta para UI)                               │
│  ├── query_data(db) → list[dict] (abstracto)                    │
│  └── write(db, output_dir) → Path                               │
│       ├── Llama query_data()                                     │
│       ├── Escribe CSV con csv.DictWriter                         │
│       └── Retorna ruta del archivo                               │
│                                                                  │
│  Registro (REGISTRY):                                            │
│  ├── "student_courses" → StudentCoursesReport                    │
│  │   └── Todas las materias de todos los estudiantes             │
│  │                                                               │
│  ├── "eligibility" → EligibilityReport                           │
│  │   └── Evaluación de elegibilidad por estudiante               │
│  │                                                               │
│  └── "student_stats" → StudentStatsReport                        │
│      └── Estadísticas pivot por carrera y semestre               │
│                                                                  │
│  generate_reports(db, output_dir, report_names?) → list[Path]  │
│    └── Itera REGISTRY, escribe cada reporte                     │
└──────────────────────────────────────────────────────────────────┘
```

### 5.7 Interfaz Web (`web/app.py` + `web/static/`)

Aplicación SPA (Single Page Application) construida con FastAPI y JavaScript vanilla.

```
┌──────────────────────────────────────────────────────────────────┐
│                    ARQUITECTURA DE LA INTERFAZ WEB             │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   index.html (SPA)                       │   │
│  │  ┌────────────────────────────────────────────────────┐  │   │
│  │  │  Tabs Nav: Pipeline | PlanEst. | Params | Elegib. │  │   │
│  │  │           Reportes | Consultas IA                  │  │   │
│  │  └────────────────────────────────────────────────────┘  │   │
│  │  ┌────────────────────────────────────────────────────┐  │   │
│  │  │          <main id="tab-content">                   │  │   │
│  │  │          (contenido dinámico vía fetch)            │  │   │
│  │  └────────────────────────────────────────────────────┘  │   │
│  │  ┌────────────────────────────────────────────────────┐  │   │
│  │  │         Footer: DB path, borrar BD                 │  │   │
│  │  └────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Cada tab se carga via: fetch("/tabs/{name}")                   │
│                                                                  │
│  Backend:                                                        │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐    │
│  │  Pipeline    │   │  Parámetros  │   │  Plan Estudios   │    │
│  │  /api/pipeline│   │  /api/params │   │  /api/study-plan │    │
│  ├──────────────┤   ├──────────────┤   ├──────────────────┤    │
│  │  Elegibilidad│   │  Reportes    │   │  Consultas IA    │    │
│  │  /api/eligib │   │  /api/reports│   │  /api/query      │    │
│  └──────────────┘   └──────────────┘   └──────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

#### Endpoints de la API Web

| Método | Ruta | Propósito |
|---|---|---|
| `GET` | `/` | Página principal (SPA) |
| `GET` | `/tabs/{tab_name}` | Carga el HTML de una pestaña |
| `POST` | `/api/pipeline/convert` | Inicia conversión PDF→MD |
| `POST` | `/api/pipeline/extract` | Inicia extracción MD→SQLite |
| `POST` | `/api/pipeline/run` | Pipeline completo |
| `POST` | `/api/pipeline/reports` | Genera todos los reportes CSV |
| `GET` | `/api/tasks/{id}/stream` | SSE de logs de tareas |
| `POST` | `/api/study-plan/import` | Importa plan de estudios (.xls) |
| `GET` | `/api/study-plan/programs` | Lista programas importados |
| `GET` | `/api/study-plan/subjects/{program}` | Materias de un programa |
| `GET` | `/api/study-plan/prerequisites/{program}` | Prelaciones de un programa |
| `GET` | `/api/parameters` | Lista parámetros del sistema |
| `POST` | `/api/parameters/set` | Crea o actualiza parámetro |
| `POST` | `/api/parameters/delete` | Elimina parámetro |
| `POST` | `/api/eligibility/evaluate` | Evalúa elegibilidad de un estudiante |
| `GET` | `/api/reports/list` | Lista reportes disponibles |
| `POST` | `/api/reports/generate/{name}` | Genera un reporte específico |
| `GET` | `/api/reports/preview/{name}` | Vista previa del reporte |
| `GET` | `/api/reports/download/{name}` | Descarga el CSV del reporte |
| `POST` | `/api/query/ask` | Consulta en lenguaje natural |
| `GET` | `/api/db/info` | Información de la base de datos |
| `POST` | `/api/db/delete` | Elimina la base de datos |

### 5.8 Consultas IA (`query.py`)

Permite realizar consultas en lenguaje natural sobre los datos académicos usando la API de Groq.

```
┌─────────────────────────────────────────────────────────────────┐
│                     CONSULTAS EN LENGUAJE NATURAL               │
│                                                                 │
│  Usuario: "¿Cuántos estudiantes tienen índice > 15?"           │
│                                                                 │
│  ask_query(db, question, model, api_key)                       │
│    │                                                            │
│    ├── 1. Obtener el esquema de la BD + muestra de datos      │
│    ├── 2. Enviar a Groq con prompt:                            │
│    │    "Genera SQL para SQLite que responda: {question}"      │
│    │    Basado en el esquema: {schema}                         │
│    ├── 3. Ejecutar el SQL generado contra la BD               │
│    ├── 4. Enviar resultados a Groq para formatear respuesta    │
│    └── 5. Retornar {sql, results, row_count, error}           │
│                                                                 │
│  Modelo por defecto: qwen-2.5-coder-32b                        │
│  Base de datos: Se inyecta el schema completo + 2 filas ejemplo│
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. Flujo de Trabajo del Usuario

```
┌──────────────────────────────────────────────────────────────────────┐
│                   FLUJO DE TRABAJO TÍPICO                          │
│                                                                      │
│  Paso 1: Colocar PDFs en data/pdfs/ y data/inscripcion/            │
│  Paso 2: Importar plan de estudios (pensum.xls)                     │
│          └── Web: Tab "Plan de Estudios" → Importar .xls           │
│                                                                      │
│  Paso 3: Configurar parámetros                                      │
│          └── Web: Tab "Parámetros" → periodo_actual                 │
│                                                                      │
│  Paso 4: Ejecutar Pipeline                                          │
│          └── Web: Tab "Pipeline" → "Ejecutar Pipeline completo"    │
│              ├── Convierte PDF → Markdown                           │
│              ├── Extrae Markdown → SQLite                           │
│              ├── Convierte inscripciones PDF → Markdown             │
│              └── Extrae inscripciones Markdown → SQLite             │
│                                                                      │
│  Paso 5: Explorar resultados                                        │
│          ├── Tab "Elegibilidad" → Evaluar estudiante por cédula    │
│          ├── Tab "Reportes" → Ver y descargar reportes CSV        │
│          └── Tab "Consultas IA" → Preguntas en lenguaje natural    │
│                                                                      │
│  Paso 6: Generar reportes CSV                                       │
│          └── Tab "Pipeline" → "Generar reportes CSV"               │
│              ├── estudiantes-materias.csv                           │
│              ├── elegibilidad.csv                                   │
│              └── estadisticas-carreras.csv                          │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 7. Dependencias Tecnológicas

### 7.1 Entorno de Ejecución

| Requisito | Versión |
|---|---|
| Python | >= 3.10 |
| SQLite | 3.x (incluido en Python) |
| Sistema Operativo | Linux, macOS, Windows |

### 7.2 Dependencias de Python

| Paquete | Propósito |
|---|---|
| `markitdown[pdf]` | Conversión de PDF a Markdown |
| `xlrd` | Lectura de archivos Excel .xls (pensum) |
| `fastapi` | Framework web para la API REST |
| `uvicorn[standard]` | Servidor ASGI |
| `jinja2` | Motor de plantillas HTML |
| `python-multipart` | Procesamiento de formularios multipart |
| `gradio` | Interfaz gráfica alternativa |
| `openai` | Cliente para API de Groq (consultas IA) |

### 7.3 Dependencias de Desarrollo

| Paquete | Propósito |
|---|---|
| `pytest` | Framework de pruebas unitarias |

---

## 8. Pruebas

El sistema cuenta con **60 pruebas unitarias** distribuidas en 5 archivos:

| Archivo | Tests | Cobertura |
|---|---|---|
| `test_eligibility.py` | 21 | Artículo 118 (a/b/c), prelaciones, helpers |
| `test_unefa_parser.py` | 12 | Parsing de transcripts UNEFA reales |
| `test_student_stats.py` | 10 | Clasificación (regular, repitiente por materia reprobada, repitiente sin retraso, desfasado por cohorte, desfasado prioritario, CINU, fallback, pivot, casos borde) |
| `test_report.py` | 7 | Generación de CSV, columnas, registro |
| `test_document_resolver.py` | 2 | Vinculación PDF-Markdown |

### Ejecución

```bash
cd academic-records-audit
source .venv/bin/activate
PYTHONPATH=src:tests python -m pytest tests/ -v
```

---

## 9. Consideraciones de Diseño

### 9.1 Separación en Dos Bases de Datos

La decisión de usar dos bases SQLite separadas (principal y parámetros) responde a:

1. **Ciclo de vida diferente**: La BD principal se regenera cada vez que se ejecuta el pipeline; los parámetros (plan de estudios) son persistentes.
2. **Portabilidad**: El plan de estudios puede compartirse entre múltiples instancias de la BD principal.
3. **Simplicidad**: Evita migraciones complejas al actualizar el plan de estudios.

### 9.2 Patrón de Diseño ReportWriter (Template Method)

La clase base `ReportWriter` define el esqueleto de generación de reportes CSV, mientras que cada subclase implementa solo la consulta de datos específica. Esto permite:

- Agregar nuevos reportes registrándolos en `REGISTRY`
- Reutilizar la lógica de escritura CSV
- Generar reportes individuales o todos a la vez

### 9.3 Pipeline Desacoplado

Cada etapa del pipeline (convertir, extraer) es independiente y puede ejecutarse por separado. Esto permite:

- Reanudar desde una etapa fallida sin reprocesar todo
- Probar cada etapa de forma aislada
- Ejecutar en paralelo la conversión de PDFs

### 9.4 SPA con JavaScript Vanilla

La interfaz web evita frameworks pesados (React, Vue) en favor de JavaScript vanilla. Cada pestaña se carga bajo demanda mediante `fetch()` y se inyecta en el DOM, manteniendo la aplicación liviana y de carga rápida.

---

## 10. Glosario

| Término | Definición |
|---|---|
| **Transcript** | Expediente académico que lista todas las materias cursadas por un estudiante con sus calificaciones |
| **Pensum** | Plan de estudios de una carrera, incluyendo materias por semestre y prelaciones |
| **Prelación** | Requisito académico: materia que debe aprobarse antes de poder cursar otra |
| **Correlación** | Materias que deben cursarse simultáneamente |
| **CINU** | Curso Integral de Nivelación Universitaria (programa de ingreso) |
| **Artículo 118** | Reglamento que define causales de NO APTO para inscripción |
| **Regular** | Estudiante que no está retrasado respecto a su cohorte de ingreso y no está repitiendo materias previamente reprobadas |
| **Repitiente** | Estudiante que en su carga académica actual tiene inscrita al menos una materia que ya cursó y reprobó en su récord académico |
| **Desfasado** | Estudiante que está al menos un semestre atrasado respecto al semestre esperado según su cohorte de ingreso (`study_plan_period`); no se gradúa con sus compañeros |
| **TEG** | Trabajo Especial de Grado |
| **UC** | Unidad de Crédito |
| **SPA** | Single Page Application (aplicación de una sola página) |
| **SSE** | Server-Sent Events (eventos enviados por el servidor) |
