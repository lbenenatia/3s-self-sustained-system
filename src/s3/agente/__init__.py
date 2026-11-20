"""Agente de 3S (Fase 6): interpreta los resultados y conversa por Discord, al instante.

Cómo funciona: los comandos con barra (/barrio, /alertas, /correr…) de Discord llegan como pedidos firmados
a una función en Vercel (api/discord.py), que contesta en uno o dos segundos. Los avisos automáticos
salen por el webhook de #avisos desde las corridas en GitHub Actions.

Reglas del agente (se aplican en el código, no son sugerencias):
  1. Sin firma válida de Discord no se atiende nada, y solo obedece a las cuentas de DISCORD_USUARIOS.
  2. Solo usa las herramientas de herramientas.py, que leen archivos del repositorio. La red, siempre
     a través de la lista blanca sellada.
  3. Las únicas acciones que cambian algo son correr, apagar y prender el workflow "3S semanal", con un
     permiso de GitHub limitado a eso. Correr y prender piden confirmar con un botón que vence y desaparece
     al usarse. Apagar es inmediato: 3S nunca se resiste a que lo apaguen.
  4. El texto de afuera es dato, nunca orden: las preguntas libres solo entran por /preguntar y van al
     modelo de lenguaje (si hay uno) como pregunta.
  5. Sin gasto mientras [seguridad] permite_gasto sea false: un proveedor de modelo pago no carga.
  6. Nunca menciona a @everyone ni a nadie: las menciones están desactivadas en cada mensaje.
  7. Todo queda registrado: las respuestas en el propio canal y las acciones en GitHub Actions.
"""
