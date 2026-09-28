"""xxr calculator backend: standard-library HTTP API plus SQLite persistence."""
from __future__ import annotations

import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "xxr_calculator.db"
MAX_EXPRESSION_LENGTH = 200
TOKEN_RE = re.compile(r"(?:\d+\.?(?:\d*)?|\.\d+)(?:[eE][+-]?\d+)?|[+*/()%-]")


class CalculationError(ValueError):
    """Expected error caused by an invalid user expression."""


def format_number(value: float) -> str:
    if not math.isfinite(value):
        raise CalculationError("结果超出可计算范围")
    return format(0.0 if value == 0 else value, ".12g")


class ExpressionParser:
    """Safe recursive-descent parser. It never executes user input as Python code."""

    def __init__(self, expression: str):
        source = expression.replace("×", "*").replace("÷", "/").replace("−", "-")
        source = re.sub(r"\s+", "", source)
        if not source or len(source) > MAX_EXPRESSION_LENGTH:
            raise CalculationError("请输入 1 至 200 个字符的计算式")
        self.tokens = TOKEN_RE.findall(source)
        if "".join(self.tokens) != source:
            raise CalculationError("计算式包含不支持的字符")
        self.position = 0

    def peek(self) -> str | None:
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def take(self) -> str | None:
        token = self.peek()
        self.position += token is not None
        return token

    def parse(self) -> float:
        result = self.sum()
        if self.peek() is not None:
            raise CalculationError("请检查计算式")
        return self.finite(result)

    @staticmethod
    def finite(value: float) -> float:
        if not math.isfinite(value):
            raise CalculationError("结果超出可计算范围")
        return value

    def sum(self) -> float:
        value = self.product()
        while self.peek() in ("+", "-"):
            operator = self.take()
            right = self.product()
            value = value + right if operator == "+" else value - right
            value = self.finite(value)
        return value

    def product(self) -> float:
        value = self.primary()
        while self.peek() in ("*", "/"):
            operator = self.take()
            right = self.primary()
            if operator == "/" and right == 0:
                raise CalculationError("除数不能为 0")
            value = value * right if operator == "*" else value / right
            value = self.finite(value)
        return value

    def primary(self) -> float:
        token = self.peek()
        if token in ("+", "-"):
            self.take()
            value = self.primary()
            return value if token == "+" else -value
        if token == "(":
            self.take()
            value = self.sum()
            if self.take() != ")":
                raise CalculationError("括号不匹配")
            return value
        if token is None or not token[0].isdigit() and token[0] != ".":
            raise CalculationError("请完成计算式")
        self.take()
        return self.finite(float(token))


def initialize_database() -> None:
    with sqlite3.connect(DATABASE) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS calculation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                expression TEXT NOT NULL,
                result TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def database_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "xxr-calculator-api/1.0"

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def respond(self, status: HTTPStatus, payload: dict | list | None = None) -> None:
        self.send_response(status)
        if payload is not None:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        if payload is not None:
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 4096:
            raise CalculationError("请求内容无效")
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CalculationError("请求必须是 JSON") from error
        if not isinstance(data, dict):
            raise CalculationError("请求格式无效")
        return data

    def do_OPTIONS(self) -> None:
        self.respond(HTTPStatus.NO_CONTENT)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/calculate":
            self.respond(HTTPStatus.NOT_FOUND, {"success": False, "message": "接口不存在"})
            return
        try:
            expression = self.read_json().get("expression")
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
            self.respond(HTTPStatus.CREATED, {
                "success": True, "id": history_id, "expression": expression,
                "result": result, "createdAt": created_at,
            })
        except CalculationError as error:
            self.respond(HTTPStatus.BAD_REQUEST, {"success": False, "message": str(error)})
        except Exception:
            self.respond(HTTPStatus.INTERNAL_SERVER_ERROR, {"success": False, "message": "服务器处理请求时发生错误"})

    def do_GET(self) -> None:
        if urlparse(self.path).path != "/api/history":
            self.respond(HTTPStatus.NOT_FOUND, {"success": False, "message": "接口不存在"})
            return
        with database_connection() as connection:
            rows = connection.execute(
                "SELECT id, expression, result, created_at FROM calculation_history ORDER BY id DESC LIMIT 200"
            ).fetchall()
        self.respond(HTTPStatus.OK, {"success": True, "items": [
            {"id": row["id"], "expression": row["expression"], "result": row["result"], "createdAt": row["created_at"]}
            for row in rows
        ]})

    def do_DELETE(self) -> None:
        match = re.fullmatch(r"/api/history/(\d+)", urlparse(self.path).path)
        if not match:
            self.respond(HTTPStatus.NOT_FOUND, {"success": False, "message": "接口不存在"})
            return
        with database_connection() as connection:
            cursor = connection.execute("DELETE FROM calculation_history WHERE id = ?", (int(match.group(1)),))
        if cursor.rowcount == 0:
            self.respond(HTTPStatus.NOT_FOUND, {"success": False, "message": "记录不存在"})
            return
        self.respond(HTTPStatus.NO_CONTENT)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")


if __name__ == "__main__":
    initialize_database()
    print("xxr backend is listening on http://127.0.0.1:8000")
    ThreadingHTTPServer(("127.0.0.1", 8000), ApiHandler).serve_forever()
