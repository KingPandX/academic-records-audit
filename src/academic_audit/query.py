from __future__ import annotations

import os
import re
import sys
from typing import Any

from openai import OpenAI

from academic_audit.database import Database

_RAG_COLUMNS: dict[str, list[str]] = {
    "program": ["students", "enrollments", "plan_subjects"],
    "code": ["courses", "plan_subjects"],
    "name": ["courses", "plan_subjects"],
    "period": ["courses", "enrollments"],
    "status": ["documents", "enrollments"],
    "course_type": ["courses"],
    "subject_type": ["plan_subjects"],
    "full_name": ["students"],
    "student_id": ["students", "courses"],
    "identity_document": ["students", "enrollments"],
}

_COLUMN_ALIASES: dict[str, str] = {
    "carrera": "program",
    "programa": "program",
    "materia": "name",
    "codigo": "code",
    "cod": "code",
    "periodo": "period",
    "estudiante": "full_name",
    "alumno": "full_name",
    "nombre": "full_name",
    "cedula": "identity_document",
    "documento": "identity_document",
    "identidad": "identity_document",
    "indice": "academic_index",
    "credito": "credits",
    "semestre": "semester",
    "tipo": "subject_type",
    "nota": "grade",
    "observacion": "observation",
}


def _open_db_at(path_str: str | None) -> Database:
    from pathlib import Path

    if path_str:
        p = Path(path_str)
    else:
        p = Path.cwd() / "data" / "audit.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    db = Database(p, memory=False)
    db.init_schema()
    return db


# ── 1. Schema introspection ──


def get_schema(db: Database) -> str:
    lines: list[str] = []
    with db.connect() as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row["name"] for row in cursor.fetchall()]

        for table in tables:
            col_info = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
            fk_info = conn.execute(f"PRAGMA foreign_key_list('{table}')").fetchall()

            cols: list[str] = []
            for col in col_info:
                parts = [col["name"], col["type"]]
                if col["pk"]:
                    parts.append("PK")
                parts.append("NOT NULL" if col["notnull"] else "NULLABLE")
                parts.append(f"default={col['dflt_value']}" if col["dflt_value"] else "")
                cols.append(" ".join(p for p in parts if p))

            fks: list[str] = []
            for fk in fk_info:
                fks.append(f"{fk['from']} → {fk['table']}({fk['to']})")

            lines.append(f"\nTABLE: {table}")
            lines.append(f"  Columns: {', '.join(cols)}")
            if fks:
                lines.append(f"  Foreign keys: {', '.join(fks)}")

            try:
                sample = conn.execute(
                    f"SELECT * FROM '{table}' LIMIT 3"
                ).fetchall()
                if sample:
                    lines.append("  Sample rows:")
                    col_names = [desc[0] for desc in conn.description]
                    for row in sample:
                        vals = ", ".join(
                            f"{n}={v}" for n, v in zip(col_names, row)
                        )
                        lines.append(f"    {vals}")
            except Exception:
                pass

    return "\n".join(lines)


# ── 2. Prompts ──


def build_system_prompt(schema: str) -> str:
    return (
        "Eres un asistente experto en SQLite. "
        "La base de datos tiene estas tablas:\n\n"
        f"{schema}\n\n"
        "Reglas:\n"
        "- Genera ÚNICAMENTE sentencias SELECT (no INSERT, UPDATE, DELETE, DROP, ALTER, CREATE)\n"
        "- Usa sintaxis SQLite válida\n"
        "- No agregues explicaciones, solo el SQL\n"
        "- Si la pregunta no se puede responder, responde con: -- NO SE PUEDE RESPONDER\n"
        "- Cuando uses IN con strings, asegúrate de usar comillas simples correctamente\n"
        "- Los nombres de tabla y columna no necesitan escaparse con caracteres especiales\n"
    )


def build_user_prompt(question: str, rag_values: str | None = None) -> str:
    prompt = f"Pregunta: {question}\n"
    if rag_values:
        prompt += (
            f"\nValores disponibles en la base de datos para usar en filtros WHERE:\n"
            f"{rag_values}\n\n"
            "Genera el SQL para responder la pregunta usando EXACTAMENTE "
            "los valores listados arriba (respeta mayúsculas, tildes y espacios)."
        )
    return prompt


# ── 3. Groq API call ──


class GroqError(Exception):
    pass


def call_groq(
    messages: list[dict[str, str]],
    model: str = "qwen-2.5-coder-32b",
    api_key: str | None = None,
) -> str:
    key = api_key or os.environ.get("GROQ_API_KEY")
    if not key:
        raise GroqError(
            "GROQ_API_KEY no configurada. "
            "Exporta la variable o pásala con --api-key"
        )

    client = OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.1,
    )
    return response.choices[0].message.content or ""


# ── 4. SQL extraction ──


def extract_sql(text: str) -> str | None:
    text = text.strip()
    if not text:
        return None

    if "-- NO SE PUEDE RESPONDER" in text.upper():
        return None

    blocks = re.findall(r"```(?:sql)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        sql = blocks[0].strip()
    else:
        sql = text.strip()

    sql = re.sub(r"^[#-]{3,}.*$", "", sql, flags=re.MULTILINE).strip()
    if sql.upper().startswith("SQL"):
        sql = sql[3:].strip()
    sql = sql.strip("`; \t\n\r")
    sql = sql.strip()
    if not sql:
        return None
    return sql + ";"


# ── 5. RAG values ──


def _detect_relevant_columns(question: str) -> list[str]:
    q_lower = question.lower()
    detected: list[str] = []
    for col in _RAG_COLUMNS:
        parts = col.lower().split("_")
        if any(p in q_lower for p in parts):
            detected.append(col)
    for alias, col in _COLUMN_ALIASES.items():
        if alias in q_lower and col not in detected:
            detected.append(col)
    return detected


def enrich_with_values(db: Database, question: str, schema: str) -> str | None:
    cols = _detect_relevant_columns(question)
    if not cols:
        return None

    results: list[str] = []
    with db.connect() as conn:
        for col in cols:
            tables = _RAG_COLUMNS.get(col, [])
            seen: set[str] = set()
            for table in tables:
                try:
                    rows = conn.execute(
                        f"SELECT DISTINCT \"{col}\" FROM \"{table}\" "
                        f"WHERE \"{col}\" IS NOT NULL AND \"{col}\" != '' "
                        f"ORDER BY 1 LIMIT 50"
                    ).fetchall()
                    for row in rows:
                        val = str(row[0])
                        if val and val not in seen:
                            seen.add(val)
                except Exception:
                    pass
            if seen:
                vals = " | ".join(sorted(seen))
                results.append(f"- {col}: {vals}")

    if not results:
        return None
    return "\n".join(results)


# ── 6. Security ──


def is_read_only(sql: str) -> bool:
    stripped = sql.strip().upper().lstrip()
    if not stripped:
        return False
    if stripped.startswith("SELECT") or stripped.startswith("PRAGMA"):
        return True
    if stripped.startswith("WITH"):
        return True
    return False


# ── 7. Format results ──


def format_results(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "(0 resultados)"

    col_widths: list[int] = []
    for i, col in enumerate(columns):
        max_w = len(str(col))
        for row in rows[:100]:
            val = str(list(row.values())[i]) if hasattr(row, "values") else str(row[i])
            if len(val) > max_w:
                max_w = len(val)
        max_w = min(max_w, 60)
        col_widths.append(max_w)

    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    header = (
        "|"
        + "|".join(f" {col:{w}} " for col, w in zip(columns, col_widths))
        + "|"
    )

    out: list[str] = [sep, header, sep.replace("-", "=")]
    for row in rows[:100]:
        vals = list(row.values()) if hasattr(row, "values") else list(row)
        cells: list[str] = []
        for i, (v, w) in enumerate(zip(vals, col_widths)):
            s = str(v) if v is not None else ""
            if len(s) > 60:
                s = s[:57] + "..."
            cells.append(f" {s:{w}} ")
        out.append("|" + "|".join(cells) + "|")
        out.append(sep)

    if len(rows) > 100:
        out.append(f"... y {len(rows) - 100} filas más")

    return "\n".join(out)


# ── 8. Interactive loop ──


def interactive_loop(
    db: Database,
    model: str = "qwen-2.5-coder-32b",
    api_key: str | None = None,
) -> None:
    import readline  # noqa: F401

    schema = get_schema(db)
    system_prompt = build_system_prompt(schema)

    print()
    print(f"  🧠 Groq · {model} · Base: {db.path}")
    print('  Escribe "salir" para terminar.')
    print()

    while True:
        try:
            question = input("  ¿Qué deseas consultar? > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not question:
            continue
        if question.lower() in ("salir", "exit", "quit"):
            break

        rag_values = enrich_with_values(db, question, schema)
        user_prompt = build_user_prompt(question, rag_values)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        print()
        print("  🤖 Consultando a la IA...", end=" ", flush=True)
        try:
            response = call_groq(messages, model, api_key)
        except Exception as e:
            print(f"\n  ❌ Error: {e}")
            continue
        print("OK")

        sql = extract_sql(response)
        if sql is None:
            print(f"  ❌ No se pudo generar SQL para esta pregunta")
            print(f"  Respuesta de la IA: {response[:200]}")
            print()
            continue

        print(f"\n  > {sql}\n")

        if not is_read_only(sql):
            print("  ⛔ Sentencia no permitida (solo SELECT/PRAGMA)")
            print()
            continue

        with db.connect() as conn:
            try:
                cursor = conn.execute(sql)
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                print(format_results(rows, columns))
            except Exception as e:
                print(f"  ❌ Error ejecutando SQL: {e}")

        print()


# ── 9. Single query ──


def ask_query(
    db: Database,
    question: str,
    model: str = "qwen-2.5-coder-32b",
    api_key: str | None = None,
) -> dict[str, Any]:
    schema = get_schema(db)
    system_prompt = build_system_prompt(schema)
    rag_values = enrich_with_values(db, question, schema)
    user_prompt = build_user_prompt(question, rag_values)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        response = call_groq(messages, model, api_key)
    except Exception as e:
        return {"sql": None, "results": None, "error": str(e)}

    sql = extract_sql(response)
    if sql is None:
        return {
            "sql": None,
            "results": None,
            "error": "No se pudo generar SQL",
            "raw_response": response[:500],
        }

    if not is_read_only(sql):
        return {"sql": sql, "results": None, "error": "Solo se permiten consultas SELECT"}

    with db.connect() as conn:
        try:
            cursor = conn.execute(sql)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            table = format_results(rows, columns)
            return {
                "sql": sql,
                "results": table,
                "error": None,
                "row_count": len(rows),
            }
        except Exception as e:
            return {"sql": sql, "results": None, "error": f"Error ejecutando SQL: {e}"}


def single_query(
    db: Database,
    question: str,
    model: str = "qwen-2.5-coder-32b",
    api_key: str | None = None,
) -> None:
    result = ask_query(db, question, model, api_key)
    if result.get("error"):
        print(f"❌ {result['error']}")
        if result.get("raw_response"):
            print(f"Respuesta de la IA: {result['raw_response']}")
        sys.exit(1)
    if result.get("sql"):
        print(f"> {result['sql']}\n")
    if result.get("results"):
        print(result["results"])
