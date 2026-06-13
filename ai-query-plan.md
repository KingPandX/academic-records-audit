# Plan: Asistente de Consultas con IA para la Base de Datos

## Resumen

Herramienta interactiva en la terminal que permite hacer preguntas en lenguaje natural sobre los datos de la base de datos. La IA (Groq + Qwen 2.5 Coder) traduce las preguntas a SQL, lo ejecuta y muestra los resultados.

Incluye **RAG de valores** (Retrieval-Augmented Generation nivel 1): antes de generar SQL, consulta la BD para obtener los valores reales de las columnas relevantes a la pregunta del usuario, y los inyecta en el prompt para evitar errores de formato (mayúsculas, tildes, espacios).

```
usuario: "estudiantes de ingeniería de sistemas"
  → RAG: SELECT DISTINCT program FROM students
  → inyecta: ['INGENIERÍA DE SISTEMAS', 'INGENIERÍA CIVIL', ...]
  → IA genera: WHERE program = 'INGENIERÍA DE SISTEMAS'
  → ejecuta SQL → muestra tabla
```

## Dependencia

- `openai` — cliente compatible con Groq (misma API que OpenAI, solo cambia `base_url`)

## Archivos a crear/modificar

| Archivo | Acción |
|---------|--------|
| `pyproject.toml` | Agregar `openai` |
| `src/academic_audit/query.py` | **Nuevo** — toda la lógica |
| `src/academic_audit/cli.py` | Agregar subcomando `query` |

---

## Componentes de `query.py`

### 1. `get_schema(db) -> str`

Introspecciona la base de datos y devuelve un texto descriptivo del esquema:

- Para cada tabla: nombre, columnas con tipos, PK, FK
- 3 filas de ejemplo por tabla (para que el LLM entienda los datos)
- Formato legible para incluir en el prompt del sistema

### 2. `build_system_prompt(schema) -> str`

Construye el prompt sistémico:

```
Eres un asistente experto en SQLite. 
La base de datos tiene estas tablas:

{esquema completo}

Reglas:
- Genera ÚNICAMENTE sentencias SELECT (no INSERT, UPDATE, DELETE, DROP, ALTER)
- Usa sintaxis SQLite válida
- No agregues explicaciones, solo el SQL
- Si la pregunta no se puede responder, responde con: -- NO SE PUEDE RESPONDER
```

### 2b. `build_user_prompt(question, rag_values) -> str`

Construye el prompt del usuario con los valores recuperados por RAG:

```
Pregunta: {question}

Valores disponibles en la base de datos para usar en filtros WHERE:
{rag_values}

Genera el SQL para responder la pregunta usando EXACTAMENTE los valores listados arriba (respeta mayúsculas, tildes y espacios).
```

### 3. `call_groq(messages, model, api_key) -> str`

Llama a la API de Groq usando el cliente OpenAI con `base_url` personalizado:

```python
client = OpenAI(
    api_key=api_key,
    base_url="https://api.groq.com/openai/v1",
)
response = client.chat.completions.create(
    model=model,
    messages=messages,
    temperature=0.1,
)
return response.choices[0].message.content
```

### 4. `extract_sql(text: str) -> str | None`

Extrae el bloque SQL de la respuesta del LLM:

- Busca bloques ```sql ... ```
- Si no encuentra, toma todo el texto como SQL
- Limpia la sentencia

### 5. `enrich_with_values(db, question, schema) -> str`

**RAG de valores**: analiza la pregunta del usuario y las columnas del esquema para detectar qué columnas de texto serán usadas en filtros (`WHERE`). Consulta los valores reales de esas columnas en la BD y genera un bloque de contexto adicional para el prompt.

```
Pregunta: "materias de ingeniería de sistemas con más de 3 créditos"

Columnas textuales en el esquema: program, student_id, code, name, period, ...
Palabras clave detectadas: "ingeniería de sistemas" → columna `program`

→ SELECT DISTINCT program FROM students ORDER BY program
→ SELECT DISTINCT program FROM plan_subjects ORDER BY program
→ Resultado: ["INGENIERÍA DE SISTEMAS", "INGENIERÍA CIVIL", ...]
```

**Columnas con RAG activo:**

| Columna | Tablas | Consulta |
|---------|--------|----------|
| `program` | students, enrollments, plan_subjects | `SELECT DISTINCT program` |
| `code` | courses, plan_subjects | `SELECT DISTINCT code` |
| `name` | courses, plan_subjects | `SELECT DISTINCT name` |
| `period` | courses, enrollments | `SELECT DISTINCT period` |
| `status` | documents, enrollments | `SELECT DISTINCT status` |
| `course_type` | courses | `SELECT DISTINCT course_type` |
| `subject_type` | plan_subjects | `SELECT DISTINCT subject_type` |
| `full_name` | students | `SELECT DISTINCT full_name` |
| `student_id` | students, courses | `SELECT DISTINCT student_id` |
| `identity_document` | students, enrollments | `SELECT DISTINCT identity_document` |

**Contexto generado** (se inyecta en el prompt del usuario):

```
Valores disponibles en la base de datos para filtros:
- program: INGENIERÍA DE SISTEMAS | INGENIERÍA CIVIL | ...
- course_type: regular | cinu
- status: pending | converted | extracted | conversion_failed
```

### 6. `is_read_only(sql: str) -> bool`

Valida que la consulta sea solo de lectura:

```python
sql_upper = sql.strip().upper()
if not sql_upper.startswith("SELECT") and not sql_upper.startswith("PRAGMA"):
    return False
return True
```

### 7. `format_results(rows, columns) -> str`

Formatea los resultados como tabla para mostrar en terminal:

- Usa `tabulate` o formateo manual con columnas
- Muestra hasta 100 filas

### 8. `interactive_loop(db, model, api_key)`

Ciclo principal REPL con RAG de valores integrado:

```
$ academic-audit query

🧠 Groq · qwen-2.5-coder-32b · Base: data/audit.db
Escribe "salir" para terminar.

¿Qué deseas consultar? > [pregunta del usuario]
  → enrich_with_values() → consulta valores reales de columnas relevantes
  → build_user_prompt(pregunta, rag_values)
  → call_groq(system_prompt + user_prompt)
  → extract_sql()
  → is_read_only()
  → ejecutar SQL
  → format_results()
  → mostrar al usuario
  → repetir
```

### 9. `single_query(db, question, model, api_key)`

Modo one-shot: misma lógica que el loop pero sin ciclo, una sola pregunta y termina.

---

## CLI (`cli.py`)

### Subcomando `query`

```
academic-audit query [opciones] [pregunta]
```

| Argumento | Descripción |
|-----------|-------------|
| `pregunta` | (opcional) Consulta directa — modo one-shot |
| `--db PATH` | Base de datos a consultar (defecto: `data/audit.db`) |
| `--model NAME` | Modelo Groq (defecto: `qwen-2.5-coder-32b`) |
| `--api-key KEY` | API key (alternativa a `GROQ_API_KEY` env) |

### Ejemplos

```bash
# Modo interactivo (REPL)
academic-audit query

# Consulta directa
academic-audit query "cuantos estudiantes hay por carrera"

# Con BD específica
academic-audit query --db data/audit.db "estudiantes con indice > 15"

# Con modelo diferente
academic-audit query --model llama-3.3-70b-versatile
```

---

## Seguridad

- **Solo lectura**: se valida que cualquier SQL generado comience con `SELECT` o `PRAGMA`
- **SQLite**: las sentencias `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE` son rechazadas antes de ejecutar
- **API key**: se lee de `GROQ_API_KEY` (variable de entorno), nunca se guarda en la BD

---

## Ejemplo de sesión real

```
$ academic-audit query

🧠 Groq · qwen-2.5-coder-32b · Base: data/audit.db
Escribe "salir" para terminar.

¿Qué deseas consultar? > ¿qué materias tiene cada estudiante?

> SELECT s.full_name, c.code, c.name, c.grade, c.period
> FROM students s
> JOIN courses c ON c.document_id = s.document_id
> ORDER BY s.full_name, c.period;
>
> ┌──────────────────────────────────┬───────────┬──────────────────────────┬───────┬──────────┐
> │            full_name             │   code    │          name           │ grade │ period  │
> ├──────────────────────────────────┼───────────┼──────────────────────────┼───────┼──────────┤
> │ RICAFLOR RODRIGUEZ, SERGIO DAVID │ ADG-25123 │ HOMBRE, SOCIEDAD...     │  17   │ 1-2021  │
> │ ...                              │           │                          │       │          │
> └──────────────────────────────────┴───────────┴──────────────────────────┴───────┴──────────┘

¿Qué deseas consultar? > salir
```

---

## Esquema de la base de datos (para referencia del prompt)

### Tablas principales

| Tabla | Descripción |
|-------|-------------|
| `documents` | Cada PDF procesado (expedientes) |
| `students` | Datos del estudiante (1 por documento) |
| `courses` | Materias cursadas |
| `academic_index_snapshots` | Índices académicos parciales |
| `document_fields` | Totales y campos extra del resumen |
| `enrollments` | Comprobantes de inscripción |
| `enrollment_subjects` | Materias inscritas en cada comprobante |

### Tablas persistentes (parámetros)

| Tabla | Descripción |
|-------|-------------|
| `parameters` | Clave → valor (periodo_actual, etc.) |
| `plan_subjects` | Materias del pensum por programa |
| `plan_prerequisites` | Prelaciones entre materias |
