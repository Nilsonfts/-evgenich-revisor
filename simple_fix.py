import sqlite3
import os

chat_id = -1002310864664
db_path = "data/bot_database.db"
os.makedirs("data", exist_ok=True)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS bot_settings (
        chat_id INTEGER PRIMARY KEY,
        enabled BOOLEAN DEFAULT TRUE,
        admin_id INTEGER,
        updated_at TEXT
    )
''')

cursor.execute('SELECT enabled FROM bot_settings WHERE chat_id = ?', (chat_id,))
result = cursor.fetchone()

if not result or not result[0]:
    cursor.execute('''
        INSERT OR REPLACE INTO bot_settings (chat_id, enabled, admin_id, updated_at)
        VALUES (?, ?, ?, datetime('now'))
    ''', (chat_id, True, 196614680))
    conn.commit()
    print(f"Bot enabled for chat {chat_id}")
else:
    print(f"Bot already enabled for chat {chat_id}")

conn.close()
print("DONE")
