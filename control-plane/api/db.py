import os
from contextlib import contextmanager

import pymssql
from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


@contextmanager
def connect():
    conn = pymssql.connect(
        server=_required("SQL_SERVER"),
        user=_required("SQL_ADMIN_LOGIN"),
        password=_required("SQL_ADMIN_PASSWORD"),
        database=_required("SQL_DATABASE"),
        port=1433,
        tds_version="7.4",
        login_timeout=60,
        timeout=60,
    )
    try:
        yield conn
    finally:
        conn.close()


def query(sql: str, params: tuple = ()):
    with connect() as conn:
        with conn.cursor(as_dict=True) as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def execute(sql: str, params: tuple = ()):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
