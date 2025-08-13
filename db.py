import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

script_dir = Path(__file__).parent
db_dir = script_dir/ "db"
db_dir.mkdir(exist_ok=True)
db_path = db_dir/"alldata.db"

@contextmanager
def get_conn():
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        yield conn

def init_db():
    with get_conn() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            surname TEXT NOT NULL,
            position TEXT,
            phone TEXT,
            email TEXT UNIQUE NOT NULL,
            company TEXT,
            address TEXT,
            notes TEXT,
            avatar_path TEXT,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            mime TEXT,
            size_bytes INTEGER,
            stored_path TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS declarations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            goods_description TEXT,
            tnved_code TEXT,
            attached_file_id INTEGER,
            meta_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(attached_file_id) REFERENCES files(id)
        )""")

def get_user_by_email(email: str):
    with get_conn() as c:
        cur = c.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = cur.fetchone()
        return dict(row) if row else None

def get_user_by_id(user_id: int):
    with get_conn() as c:
        cur = c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    
def update_user(user_id: int, **fields):
    if not fields:
        return
    cols = []
    vals = []
    for k, v in fields.items():
        if k not in {"name","surname","position","phone","email","company","address","notes","avatar_path","password"}:
            continue
        cols.append(f"{k} = ?")
        vals.append(v)
    if not cols:
        return
    vals.append(user_id)
    with get_conn() as c:
        c.execute(
            f"""
            UPDATE users
               SET {", ".join(cols)},
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = ?
            """,
            vals,
        )    

def create_user(name: str,surname: str,email: str,password: str,position: Optional[str] = None,phone: Optional[str] = None,company: Optional[str] = None,
                address: Optional[str] = None,notes: Optional[str] = None,avatar_path: Optional[str] = None):
    with get_conn() as c:
        c.execute(
            """
            INSERT INTO users (name, surname, position, phone, email, company, address, notes, avatar_path, password)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, surname, position, phone, email, company, address, notes, avatar_path, password),
        )

def add_file(user_id:int, filename:str, mime:str, size:int, stored_path:str):
    with get_conn() as c:
        c.execute("""INSERT INTO files(user_id, filename, mime, size_bytes, stored_path)
                     VALUES(?,?,?,?,?)""", (user_id, filename, mime, size, stored_path))

def list_files(user_id:int, limit=200):
    with get_conn() as c:
        cur = c.execute("""SELECT id, filename, mime, size_bytes, stored_path, created_at
                           FROM files WHERE user_id = ? ORDER BY created_at DESC LIMIT ?""", (user_id, limit))
        return [dict(r) for r in cur.fetchall()]

def add_declaration(user_id:int, title:str, goods_description:str, tnved_code:str, attached_file_id, meta_json:str):
    with get_conn() as c:
        c.execute("""INSERT INTO declarations(user_id,title,goods_description,tnved_code,attached_file_id,meta_json)
                     VALUES(?,?,?,?,?,?)""", (user_id, title, goods_description, tnved_code, attached_file_id, meta_json))

def list_declarations(user_id:int, limit=200):
    with get_conn() as c:
        cur = c.execute("""SELECT d.id, d.title, d.goods_description, d.tnved_code,
                                  d.attached_file_id, d.created_at, f.filename AS file_name
                           FROM declarations d
                           LEFT JOIN files f ON f.id = d.attached_file_id
                           WHERE d.user_id = ? ORDER BY d.created_at DESC LIMIT ?""", (user_id, limit))
        return [dict(r) for r in cur.fetchall()]

def get_user_profile(user_id:int):
    with get_conn() as c:
        cur = c.execute("SELECT * FROM user_profile WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    
def upsert_user_profile(user_id:int, data:dict):
    keys = ["first_name","last_name","position","phone","email","company","address","notes","avatar_path"]
    vals = [data.get(k) for k in keys]
    with get_conn() as c:
        c.execute(f"""
        INSERT INTO user_profile (user_id, {",".join(keys)})
        VALUES (?, {",".join("?"*len(keys))})
        ON CONFLICT(user_id) DO UPDATE SET
            {", ".join([f"{k}=excluded.{k}" for k in keys])},
            updated_at = CURRENT_TIMESTAMP
        """, (user_id, *vals))

def add_file(user_id:int, filename:str, mime:str, size:int, stored_path:str):
    with get_conn() as c:
        c.execute(
            "INSERT INTO files(user_id, filename, mime, size_bytes, stored_path) VALUES(?,?,?,?,?)",
            (user_id, filename, mime, size, stored_path),)

def list_files(user_id:int, limit=200):
    with get_conn() as c:
        cur = c.execute(
            """SELECT id, filename, mime, size_bytes, stored_path, created_at
               FROM files WHERE user_id = ? ORDER BY created_at DESC LIMIT ?""",
            (user_id, limit),
        )
        return [dict(r) for r in cur.fetchall()]

def add_declaration(user_id:int, title:str, goods_description:str, tnved_code:str, attached_file_id, meta_json:str):
    with get_conn() as c:
        c.execute(
            """INSERT INTO declarations(user_id,title,goods_description,tnved_code,attached_file_id,meta_json)
               VALUES(?,?,?,?,?,?)""",
            (user_id, title, goods_description, tnved_code, attached_file_id, meta_json),
        )

def list_declarations(user_id:int, limit=200):
    with get_conn() as c:
        cur = c.execute(
            """SELECT d.id, d.title, d.goods_description, d.tnved_code,
                      d.attached_file_id, d.created_at, f.filename AS file_name
               FROM declarations d
               LEFT JOIN files f ON f.id = d.attached_file_id
               WHERE d.user_id = ? ORDER BY d.created_at DESC LIMIT ?""",
            (user_id, limit),
        )
        return [dict(r) for r in cur.fetchall()]