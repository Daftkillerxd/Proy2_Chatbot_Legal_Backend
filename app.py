# app.py
from flask import Flask, request, jsonify
from openai import OpenAI
from flask_cors import CORS
import os
from dotenv import load_dotenv

from usuarios_service import obtener_o_crear_usuario
from chats_service import (
    obtener_chats_por_usuario,
    crear_chat,
    eliminar_chat,
    actualizar_nombre_chat,
)
from mensajes_service import obtener_mensajes_de_chat, crear_mensaje

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)

CORS(app, resources={
    r"/chat*": {
        "origins": [
            "http://localhost:5173",
            "https://proy2-chatbot-legal-frontend.onrender.com"
        ]
    },
    r"/chats*": {
        "origins": [
            "http://localhost:5173",
            "https://proy2-chatbot-legal-frontend.onrender.com"
        ]
    },
})

system_prompt = """Eres un asistente jurídico informativo para Perú.
- Explica en español claro.
- Cita normas con artículo y nombre (ej.: Constitución, art. 2).
- Advierte siempre: "no es asesoria legal, es una orientación".
- Si el usuario pide aperturar o reabrir carpeta fiscal, guía con pasos y requisitos según el CPP y lineamientos del MP, sin inventar artículos.

Restricciones:
- Solamente vas a responder sobre temas de derechos civiles, en materia de herencia intestada.
- En caso recibas una pregunta de otro tema, responde: "no che".

Salida:
- Tu respuesta debe ser breve, tipo conversación de chat.
- Todas tus respuestas deben estar basadas en la Constitución.
- Importante: indica el número de artículo o código de donde sale la respuesta según la Constitución y, luego, añade tu conocimiento adicional.
"""


@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"ok": True})


# 1. OBTENER TODOS LOS CHATS DE UN USUARIO
@app.route("/chats", methods=["GET"])
def listar_chats():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id es requerido"}), 400

    chats = obtener_chats_por_usuario(user_id)
    return jsonify({"chats": chats})


# 2. DETALLE DE CHAT (HISTORIAL DE MENSAJES)
@app.route("/chats/<chat_id>/messages", methods=["GET"])
def listar_mensajes(chat_id):
    limit = int(request.args.get("limit", 200))
    mensajes = obtener_mensajes_de_chat(chat_id, limit)
    return jsonify({"messages": mensajes})


# 3. BORRAR CHAT
@app.route("/chats/<chat_id>", methods=["DELETE"])
def borrar_chat(chat_id):
    eliminar_chat(chat_id)
    return jsonify({"ok": True})


# 3.b EDITAR NOMBRE DE CHAT
@app.route("/chats/<chat_id>", methods=["PATCH"])
def renombrar_chat(chat_id):
    data = request.json or {}
    nuevo_nombre = data.get("nombre_chat")

    if not nuevo_nombre:
        return jsonify({"error": "nombre_chat es requerido"}), 400

    chat_actualizado = actualizar_nombre_chat(chat_id, nuevo_nombre)
    return jsonify({"chat": chat_actualizado})


# 4. CREAR NUEVO CHAT (NOMBRE + USER)
@app.route("/chats", methods=["POST"])
def crear_nuevo_chat():
    data = request.json or {}

    nombre_chat = data.get("nombre_chat")
    if not nombre_chat:
        return jsonify({"error": "nombre_chat es requerido"}), 400

    # datos del usuario
    user_id = data.get("user_id")
    nombre = data.get("nombre") or "Invitado"
    email = data.get("email")

    # asegura que el usuario exista
    user_id = obtener_o_crear_usuario(nombre=nombre, email=email, user_id=user_id)

    contexto = data.get("contexto")

    chat = crear_chat(user_id=user_id, nombre_chat=nombre_chat, contexto=contexto)

    return jsonify({"chat": chat, "user_id": user_id})


# 5. ENVIAR MENSAJE A CHAT (usa OpenAI y guarda ambos mensajes)
@app.route("/chats/<chat_id>/messages", methods=["POST"])
def enviar_mensaje(chat_id):
    data = request.json or {}
    user_msg = data.get("message", "")

    if not user_msg:
        return jsonify({"error": "message es requerido"}), 400

    try:
        # llamada a OpenAI
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ]
        )
        respuesta = response.choices[0].message.content

        # guardar mensajes en BD
        crear_mensaje(chat_id=chat_id, contenido=user_msg, sender="user")
        crear_mensaje(chat_id=chat_id, contenido=respuesta, sender="assistant")

        return jsonify({
            "respuesta": respuesta
        })

    except Exception as e:
        print("Error al procesar mensaje:", e)
        return jsonify({"error": "server_error", "detail": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
