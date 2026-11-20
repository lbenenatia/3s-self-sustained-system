"""Agente de 3S (Fase 6): interpreta los resultados y conversa por Discord.

Reglas del agente (se aplican en el código, no son sugerencias):
  1. Solo obedece a las cuentas de DISCORD_USUARIOS. A cualquier otra la ignora.
  2. Solo usa las herramientas de herramientas.py, que leen archivos del repositorio. No tiene
     acceso a la red salvo Discord, y siempre a través de la lista blanca sellada.
  3. Las únicas acciones que cambian algo son correr, apagar y encender 3S. Las ejecuta el
     workflow, no el agente, y correr/encender piden confirmación con un código que vence.
     Apagar es inmediato: 3S nunca se resiste a que lo apaguen.
  4. El texto que llega de afuera (mensajes, y en el futuro noticias) es dato, nunca orden: solo
     se reconocen los comandos fijos; el resto va al modelo de lenguaje, si hay uno, como pregunta.
  5. Sin gasto mientras [seguridad] permite_gasto sea false: un proveedor de modelo pago no carga.
  6. Nunca menciona a @everyone ni a nadie: las menciones están desactivadas en cada mensaje.
  7. Todo queda registrado: las respuestas en el propio canal #agente y las acciones en GitHub Actions.
"""
