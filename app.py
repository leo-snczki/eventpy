import os
from flask import Flask, g, render_template, request, redirect, url_for, session, flash
from flask_bootstrap import Bootstrap5
from datetime import datetime
from models import Recibo, Utilizador, Evento, Lugar, Venda, Bilhete, db
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


# Variaveis globais para templates, por algum motivo nao funciona se colocar no base
@app.context_processor
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

    query = (
        Evento
        .select(
            Evento,
            fn.MIN(Lugar.preco_base).alias("preco_min"),
            fn.MAX(Lugar.preco_base).alias("preco_max"),
        )
        .join(Lugar, JOIN.LEFT_OUTER)
        .group_by(Evento)
    )

    args = request.args

    if args.get("tipo"):
        filtros.append(Evento.tipo == args["tipo"])

    if args.get("nome"):
        filtros.append(Evento.titulo.contains(args["nome"]))

    if args.get("local"):
        filtros.append(Evento.local.contains(args["local"])) 

    if args.get("preco_min"):
        query = query.where(Lugar.preco_base >= float(args["preco_min"]))

    if args.get("preco_max"):
        query = query.where(Lugar.preco_base <= float(args["preco_max"]))

    if filtros:
        query = query.where(*filtros)

    duracao = args.get("duracao")
    if duracao == "120+":
        query = query.where(Evento.duracao > 120)
    elif duracao:
        min_d, max_d = duracao.split("-")
        query = query.where(Evento.duracao.between(int(min_d), int(max_d)))

    return render_template("eventos.html", eventos=query)

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

@app.route("/escolher_lugar/<int:evento_id>", methods=["GET", "POST"])
def escolher_lugar(evento_id):
    if g.utilizador is None:
        flash("Precisa de iniciar sessão para comprar bilhetes.", "warning")
        return redirect(url_for("login"))
    evento = Evento.get_or_none(Evento.id == evento_id)
    if evento.tipo == Evento.TIPO_CONCERTO:
        return redirect(url_for("login", evento_id=evento.id))
    if not evento:
        flash("O evento não existe.", "warning")
        return redirect(url_for("eventos"))

    # Captura a fila selecionada via GET
    fila_selecionada = request.args.get("fila")

    # Pega todas as filas disponíveis do evento (não vendidas)
    filas_query = (
        Lugar
        .select(Lugar.fila)
        .where((Lugar.evento == evento) & (Lugar.vendido == False) & (Lugar.fila.is_null(False)))
        .distinct()
        .order_by(Lugar.fila)
    )
    filas = [f.fila for f in filas_query]

    lugares = []
    if fila_selecionada:
        lugares = (
            Lugar
            .select()
            .where((Lugar.evento == evento) & (Lugar.fila == fila_selecionada))
            .order_by(Lugar.numero)
        )

    # Processa o POST de confirmação de lugares
    if request.method == "POST":
        selecionados = request.form.getlist("lugares_selecionados")
        if not selecionados:
            flash("Selecione pelo menos um lugar.", "warning")
        else:
            #
            # Marca os lugares como vendidos mas ainda nao cria venda/bilhetes
            for lugar_id in selecionados:
                lugar = Lugar.get_or_none(Lugar.id == int(lugar_id))
                if lugar and not lugar.vendido:
                    lugar.vendido = True
                    lugar.save()
            flash(f"{len(selecionados)} lugar/es confirmado/s com sucesso!", "success")
            # Redireciona para evitar reenvio de formulário
            return redirect(url_for("escolher_lugar", evento_id=evento.id, fila=fila_selecionada))

    return render_template(
        "escolher_lugar.html",
        evento=evento,
        filas=filas,
        fila_selecionada=fila_selecionada,
        lugares=lugares
    )

@app.route("/suporte")
def suporte():
    return render_template("suporte.html")

if __name__ == "__main__":
    app.run(debug=True)
