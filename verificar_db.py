import sqlite3

conexion = sqlite3.connect("red_valiente.db")

print("TABLAS DE LA BASE DE DATOS:")

tablas = conexion.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type = 'table'
    ORDER BY name
""").fetchall()

for tabla in tablas:
    print("-", tabla[0])

print("\nCANTIDAD DE REGISTROS:")

for nombre in ["usuarias", "vacantes", "postulaciones"]:
    existe = conexion.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (nombre,)
    ).fetchone()

    if existe:
        cantidad = conexion.execute(
            f'SELECT COUNT(*) FROM "{nombre}"'
        ).fetchone()[0]

        print(f"{nombre}: {cantidad}")

conexion.close()
