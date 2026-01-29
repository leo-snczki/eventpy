import os
from flask import Flask, g, render_template, request, redirect, url_for, session
from flask_bootstrap import Bootstrap5
from datetime import datetime
from models import Utilizador, Evento, Lugar
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

@app.route("/carrinho")
def carrinho():
    return render_template("carrinho.html")

@app.route("/eventos")
def eventos():
    filtros = []
    query = Evento.select()

    args = request.args

    if args.get("tipo"):
        filtros.append(Evento.tipo == args["tipo"])

    if args.get("nome"):
        filtros.append(Evento.titulo.contains(args["nome"]))

    if args.get("local"):
        filtros.append(Evento.local.contains(args["local"]))

    if filtros:
        query = query.where(*filtros)

    preco = request.args.get("preco")

    if preco:
        query = (
            Evento
            .select(Evento, fn.MIN(Lugar.preco_base).alias("preco_min"))
            .join(Lugar)
            .group_by(Evento)
        )

        if preco == "asc":
            query = query.order_by(fn.MIN(Lugar.preco_base).asc())

        elif preco == "desc":
            query = query.order_by(fn.MIN(Lugar.preco_base).desc())

        else:
            min_p, max_p = preco.split("-")
            query = query.having(
                fn.MIN(Lugar.preco_base).between(int(min_p), int(max_p))
            )

    duracao = args.get("duracao")
    if duracao == "120+":
        query = query.where(Evento.duracao > 120)
    elif duracao:
        min_d, max_d = duracao.split("-")
        query = query.where(Evento.duracao.between(int(min_d), int(max_d)))

    return render_template("eventos.html", eventos=query)

@app.route("/comprar_bilhetes/<int:id>")
def comprar_bilhetes(id):
    evento = Evento.get(Evento.id == id)

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