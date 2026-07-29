import sqlite3
conn = sqlite3.connect("alert_state.db")
print("ath_state:")
for r in conn.execute("SELECT * FROM ath_state").fetchall():
    print(r)
print("\ntrigger_state:")
for r in conn.execute("SELECT * FROM trigger_state").fetchall():
    print(r)
print("\nmeta:")
for r in conn.execute("SELECT * FROM meta").fetchall():
    print(r)
conn.close()
