import os
from flask import Flask, g, render_template, request, redirect, url_for, session
from flask_bootstrap import Bootstrap5
from datetime import datetime
from models import Utilizador
from dotenv import load_dotenv
from peewee import *

load_dotenv()

app = Flask(__name__)
bootstrap = Bootstrap5(app)
app.secret_key = os.getenv("SECRET_KEY")

@app.before_request
def carregar_utilizador():
    user_id = session.get("user_id")
    if user_id:
        try:
            g.utilizador = Utilizador.get(Utilizador.id == user_id)
        except Utilizador.DoesNotExist:
            g.utilizador = None
    else:
        g.utilizador = None

@app.context_processor # Variaveis globais para templates, por algum motivo nao funciona se colocar no base
def inject_current_year():
    return {"current_year": datetime.now().year}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        senha = request.form["senha"]
        try:
            user = Utilizador.get(Utilizador.email == email)
            if user.verificar_senha(senha):
                session["user_id"] = user.id
                return redirect(url_for("utilizador"))
        except Utilizador.DoesNotExist:
            pass
    return render_template("login.html")

@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nome = request.form["nome"]
        email = request.form["email"]
        telefone = request.form["telefone"]
        documento_identificacao = request.form["documento_identificacao"]
        senha = request.form["senha"]
        user = Utilizador(
            nome=nome,
            email=email,
            telefone=telefone,
            documento_identificacao=documento_identificacao,
        )
        user.set_senha(senha)
        user.save()
        return redirect(url_for("login"))
    return render_template("registro.html")

@app.route("/compra")
def compra():
    return render_template("compra.html")

@app.route("/utilizador")
def utilizador():
    if g.utilizador is None:
        return redirect(url_for("login"))
    return render_template("utilizador.html", utilizador=g.utilizador)

@app.route("/apagar_conta", methods=["POST"])
def apagar_conta():
    if g.utilizador is None:
        return redirect(url_for("login"))
    
    user = g.utilizador
    session.pop("user_id", None)
    user.delete_instance()
    return redirect(url_for("registro"))

@app.route("/sobre")
def sobre():
    return render_template("sobre.html")

@app.route("/suporte")
def suporte():
    return render_template("suporte.html")

if __name__ == "__main__":
    app.run(debug=True)