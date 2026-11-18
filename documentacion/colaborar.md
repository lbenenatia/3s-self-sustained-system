# Cómo colaborar

## Flujo de trabajo
1. **Nunca se trabaja directo sobre `main`.** `main` es producción: lo que está ahí corre cada lunes.
2. Creá una rama: `git checkout -b mejora/nombre-corto`.
3. Hacé el cambio y probalo localmente:
   ```bash
   python run.py --solo-datos
   python tests/test_prospectivo.py
   python tests/test_territorio.py
   python run.py                  # si tocaste modelos o señales
   ```
4. Subí la rama y abrí un **pull request**. El workflow **3S pruebas** corre solo.
5. La otra persona del equipo lo revisa y lo aprueba. Recién ahí se fusiona.

## Reglas que no se negocian
- **Datos:** nada de `data/`, `.csv` crudos, `.zip` ni `.parquet` al repositorio. El `.gitignore` lo impide; no lo fuerces con `git add -f`.
- **Secretos:** ni tokens ni claves en el código. Van en los secretos de GitHub.
- **Datos de personas:** las señales son conteos agregados por barrio y período. Las guardas bloquean campos como edad, sexo, nacionalidad, antecedentes o identificadores.
- **Cambiar las reglas de seguridad** (`guardas.py` o la sección `[seguridad]` de `config.toml`) requiere volver a sellar con `python run.py --sellar` y hacer commit de `state/sello.json`. Ese PR lo revisan las dos personas con especial cuidado.
- **El registro de predicciones es inmutable.** Nunca se edita ni se borra un archivo de `registro_predicciones/trimestral/`: su valor está en que su fecha es verificable.
- **Dependencias:** las versiones están fijas en `requirements.txt`. Cambiarlas es un PR aparte, con todas las pruebas.

## Agregar una señal nueva
1. Si viene de una fuente nueva: agregala en `[descargas]` de `config.toml`, sumá su dominio a la lista blanca (y volvé a sellar) y declará su contrato en `contratos.py`.
2. Construí la señal en `features.py` como un conjunto nuevo en `CONJUNTOS`.
3. No hace falta tocar nada más: compite sola contra el campeón en la próxima corrida y solo gana si la mejora es segura.

## Estilo
- Código y comentarios en español.
- Toda función que lea datos externos tiene que fallar con un mensaje claro y nunca tumbar la corrida entera. El campeón anterior sigue vigente.
