import sqlite3

conn = sqlite3.connect("ollama_twitter.db")
cur = conn.cursor()
cur.execute("PRAGMA table_info(trace)")
print([r for r in cur.fetchall()])
conn.close()
