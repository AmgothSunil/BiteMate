import os
import sys
import json
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from dotenv import load_dotenv
from contextlib import contextmanager
from typing import List, Dict, Optional, Generator

# Internal imports (keep yours)
from src.bitemate.utils.params import load_params
from src.bitemate.core.logger import setup_logger
from src.bitemate.core.exception import AppException

load_dotenv()

CONFIG_REL_PATH = "src/bitemate/config/params.yaml"

class PostgresManager:
    """
    Manages PostgreSQL interactions using a connection pool.
    """

    def __init__(self, config_path: Optional[str] = None, minconn: int = 1, maxconn: int = 20):
        try:
            path_to_load = config_path if config_path else CONFIG_REL_PATH
            self.params = load_params(path_to_load)
            self.db_params = self.params.get('postgre_memory_db', {})

            log_file = self.db_params.get("file_path", "database.log")
            self.logger = setup_logger(name="PostgresManager", log_file_name=log_file)

            self.logger.info("Initializing PostgreSQL Connection Pool...")

            # Use ThreadedConnectionPool (or SimpleConnectionPool) instead of psycopg2.connect()
            self.connection_pool = ThreadedConnectionPool(
                minconn,
                maxconn,
                dbname=os.getenv("PG_DB_NAME"),
                user=os.getenv("PG_USER"),
                password=os.getenv("PG_PASSWORD"),
                host=os.getenv("PG_HOST", "127.0.0.1"),
                port=os.getenv("PG_PORT", "5432")
            )

            if self.connection_pool:
                self.logger.info("Connection pool created successfully.")

            self._initialize_schema()

        except Exception as e:
            msg = f"Failed to initialize PostgresManager: {e}"
            if hasattr(self, 'logger'):
                self.logger.critical(msg)
            else:
                print(f"CRITICAL: {msg}")
            raise AppException(msg, sys)

    @contextmanager
    def get_cursor(self) -> Generator:
        """
        Yield a cursor from the pool and handle commit/rollback + return to pool.
        Usage:
            with self.get_cursor() as cursor:
                cursor.execute(...)
        """
        conn = None
        cursor = None
        try:
            # get a connection from the pool (this is why we use ThreadedConnectionPool)
            conn = self.connection_pool.getconn()
            cursor = conn.cursor()
            yield cursor
            conn.commit()
        except psycopg2.Error as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            self.logger.error(f"Database Transaction Error: {e}")
            raise AppException(f"DB Error: {e}", sys)
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            self.logger.error(f"Unexpected Error in DB Transaction: {e}")
            raise AppException(e, sys)
        finally:
            # close cursor and put the connection back in the pool
            try:
                if cursor:
                    cursor.close()
            except Exception:
                pass
            if conn:
                try:
                    self.connection_pool.putconn(conn)
                except Exception as pe:
                    self.logger.warning(f"Failed to return connection to pool: {pe}")

    def _initialize_schema(self):
        create_table_query = """
        CREATE TABLE IF NOT EXISTS chat_history (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(50) NOT NULL,
            session_id VARCHAR(50) NOT NULL,
            role VARCHAR(20) CHECK (role IN ('user', 'assistant', 'system')),
            content TEXT NOT NULL,
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_chat_history_session 
        ON chat_history (user_id, session_id, created_at DESC);
        """
        with self.get_cursor() as cursor:
            cursor.execute(create_table_query)
            self.logger.debug("Schema 'chat_history' verified.")

    def add_message(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict] = None
    ):
        json_meta = json.dumps(metadata) if metadata else '{}'

        query = """
            INSERT INTO chat_history (user_id, session_id, role, content, metadata)
            VALUES (%s, %s, %s, %s, %s)
        """
        with self.get_cursor() as cursor:
            cursor.execute(query, (user_id, session_id, role, content, json_meta))

        self.logger.debug(f"Logged message for session {session_id} (Role: {role})")

    def get_session_history(self, user_id: str, session_id: str, limit: int = 10) -> List[Dict]:
        query = """
            SELECT role, content 
            FROM chat_history 
            WHERE user_id = %s AND session_id = %s 
            ORDER BY created_at DESC 
            LIMIT %s
        """
        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, (user_id, session_id, limit))
                rows = cursor.fetchall()

            history = [{"role": row[0], "content": row[1]} for row in reversed(rows)]
            return history

        except Exception as e:
            self.logger.error(f"Failed to fetch history: {e}")
            return []

    def format_history_for_llm(self, history: List[Dict]) -> str:
        formatted_text = ""
        for msg in history:
            role_label = "User" if msg['role'] == 'user' else "AI"
            formatted_text += f"{role_label}: {msg['content']}\n"
        return formatted_text

    def close(self):
        """Close the connection pool on shutdown."""
        if hasattr(self, "connection_pool") and self.connection_pool:
            try:
                self.connection_pool.closeall()
            except Exception as e:
                self.logger.warning(f"Error closing connection pool: {e}")
            else:
                self.logger.info("PostgreSQL connection pool closed.")
