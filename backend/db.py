import os
import sqlite3

base_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(base_dir, "shiftsense.db")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 1. Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

if not tables:
    print("No tables found in database.")
    conn.close()
    exit()

for (table_name,) in tables:
    print("\n" + "="*50)
    print(f"TABLE: {table_name}")
    print("="*50)

    # 2. Table schema
    print("\nColumns:")
    cursor.execute(f"PRAGMA table_info('{table_name}');")
    columns = cursor.fetchall()

    for col in columns:
        cid, name, dtype, notnull, default, pk = col
        pk_tag = " [PK]" if pk else ""
        nn_tag = " NOT NULL" if notnull else ""
        print(f"  - {name} ({dtype}){nn_tag}{pk_tag}")

    # 3. Row count
    cursor.execute(f"SELECT COUNT(*) FROM '{table_name}';")
    count = cursor.fetchone()[0]
    print(f"\nTotal Rows: {count}")

    # 4. Sample data
    print("\nSample Data (first 5 rows):")
    cursor.execute(f"SELECT * FROM '{table_name}' LIMIT 5;")
    rows = cursor.fetchall()

    if rows:
        for row in rows:
            print(" ", row)
    else:
        print("  (No data in table)")

conn.close()