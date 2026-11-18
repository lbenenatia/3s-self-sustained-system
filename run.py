"""Punto de entrada de 3S.

  python run.py               corre el ciclo completo (todos los escenarios)
  python run.py semanal       corre solo un escenario
  python run.py --sellar      (humano) aprueba las reglas de seguridad actuales
  python run.py --apagar      activa el interruptor de apagado
  python run.py --encender    lo desactiva
  python run.py --latido      avisa si hace más de 10 días que no hay una corrida exitosa
  python run.py --solo-datos  descarga y prepara los datos sin entrenar (para las pruebas)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src" / "s3"))
import guardas  # noqa: E402

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--sellar" in args:
        guardas.sellar()
    elif "--apagar" in args:
        guardas.STOP.parent.mkdir(exist_ok=True)
        guardas.STOP.write_text("apagado por un humano\n")
        print("[3S] interruptor de apagado activado")
    elif "--encender" in args:
        guardas.STOP.unlink(missing_ok=True)
        print("[3S] interruptor de apagado desactivado")
    elif "--latido" in args:
        from avisos import latido
        sys.exit(0 if latido() else 1)
    elif "--solo-datos" in args:
        from orquestador import preparar_datos
        sys.exit(0 if preparar_datos() else 1)
    else:
        from orquestador import correr
        estado, _ = correr(args or None)
        sys.exit(0 if estado == "ok" else 1)
