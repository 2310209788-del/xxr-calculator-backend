"""WSGI entry point for hosts such as PythonAnywhere."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Callable

from server import CalculationError, ExpressionParser, database_connection, format_number, initialize_database

initialize_database()

CORS_HEADERS = [
    ("Access-Control-Allow-Origin", "*"),
    ("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS"),
    ("Access-Control-Allow-Headers", "Content-Type"),
]


def json_response(
    start_response: Callable,
    status: HTTPStatus,
    payload: dict | None = None,
) -> list[bytes]:
    body = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = CORS_HEADERS + [("Content-Length", str(len(body)))]
    if payload is not None:
        headers.append(("Content-Type", "application/json; charset=utf-8"))
    start_response(f"{status.value} {status.phrase}", headers)
    return [body]


def application(environ: dict, start_response: Callable) -> list[bytes]:
    """Serve the calculator JSON API through a standard WSGI host."""
    method = environ.get("REQUEST_METHOD", "GET").upper()
    path = environ.get("PATH_INFO", "")
    if method == "OPTIONS":
        return json_response(start_response, HTTPStatus.NO_CONTENT)

    if method == "POST" and path == "/api/calculate":
        try:
            length = int(environ.get("CONTENT_LENGTH") or "0")
            if length <= 0 or length > 4096:
                raise CalculationError("请求内容无效")
            try:
                data = json.loads(environ["wsgi.input"].read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise CalculationError("请求必须是 JSON") from error
            expression = data.get("expression") if isinstance(data, dict) else None
            if not isinstance(expression, str):
                raise CalculationError("expression 必须是字符串")
            result = format_number(ExpressionParser(expression).parse())
            created_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
            with database_connection() as connection:
                cursor = connection.execute(
                    "INSERT INTO calculation_history(expression, result, created_at) VALUES (?, ?, ?)",
                    (expression, result, created_at),
                )
                history_id = cursor.lastrowid
            return json_response(start_response, HTTPStatus.CREATED, {
                "success": True, "id": history_id, "expression": expression,
                "result": result, "createdAt": created_at,
            })
        except CalculationError as error:
            return json_response(start_response, HTTPStatus.BAD_REQUEST, {"success": False, "message": str(error)})
        except Exception:
            return json_response(start_response, HTTPStatus.INTERNAL_SERVER_ERROR, {"success": False, "message": "服务器处理请求时发生错误"})

    if method == "GET" and path == "/api/history":
        with database_connection() as connection:
            rows = connection.execute(
                "SELECT id, expression, result, created_at FROM calculation_history ORDER BY id DESC LIMIT 200"
            ).fetchall()
        return json_response(start_response, HTTPStatus.OK, {"success": True, "items": [
            {"id": row["id"], "expression": row["expression"], "result": row["result"], "createdAt": row["created_at"]}
            for row in rows
        ]})

    if method == "DELETE":
        match = re.fullmatch(r"/api/history/(\d+)", path)
        if match:
            with database_connection() as connection:
                cursor = connection.execute("DELETE FROM calculation_history WHERE id = ?", (int(match.group(1)),))
            if cursor.rowcount == 0:
                return json_response(start_response, HTTPStatus.NOT_FOUND, {"success": False, "message": "记录不存在"})
            return json_response(start_response, HTTPStatus.NO_CONTENT)

    return json_response(start_response, HTTPStatus.NOT_FOUND, {"success": False, "message": "接口不存在"})
