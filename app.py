import os
from flask import Flask, g, render_template, request, redirect, url_for, session, flash
from flask_bootstrap import Bootstrap5
from flask_mail import Mail, Message
from datetime import datetime
from models import Recibo, Utilizador, Evento, Lugar, Venda, Bilhete, db
from dotenv import load_dotenv
from peewee import *

load_dotenv()

app = Flask(__name__)
bootstrap = Bootstrap5(app)
app.secret_key = os.getenv("SECRET_KEY")
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_USERNAME")

mail = Mail(app)

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

@app.route("/checkout_comprar_agora/<int:evento_id>", methods=["GET", "POST"])
def checkout_comprar_agora(evento_id):
    if g.utilizador is None:
        flash("Precisa de iniciar sessão para comprar.", "warning")
        return redirect(url_for("login"))

    evento = Evento.get_or_none(Evento.id == evento_id)
    if not evento:
        flash("Evento não encontrado.", "danger")
        return redirect(url_for("eventos"))

    lugar_sugerido = None
    filas = []
    lugares_da_fila = []
    fila_selecionada = request.args.get("fila")

    if evento.tipo == Evento.TIPO_CONCERTO:
        # Pega o lugar de pista mais barato
        lugar_sugerido = (Lugar.select()
                          .where((Lugar.evento == evento) & (Lugar.tipo == Lugar.TIPO_PISTA) & (Lugar.vendido == False))
                          .order_by(Lugar.preco_base.asc()).first())
    else:
        # Lógica de Teatro/Palestra: Carregar Filas
        filas_query = (Lugar.select(Lugar.fila)
                       .where((Lugar.evento == evento) & (Lugar.fila.is_null(False)))
                       .distinct().order_by(Lugar.fila))
        filas = [f.fila for f in filas_query]

        if fila_selecionada:
            lugares_da_fila = (Lugar.select()
                               .where((Lugar.evento == evento) & (Lugar.fila == fila_selecionada))
                               .order_by(Lugar.numero))

    if request.method == "POST":
        lugar_id = request.form.get("lugar_id")
        nif = request.form.get("nif")

        if not lugar_id:
            flash("Selecione um lugar antes de confirmar.", "warning")
        else:
            try:
                with db.atomic():
                    lugar = Lugar.get_by_id(lugar_id)
                    if lugar.vendido:
                        flash("Este lugar já não está disponível.", "danger")
                        return redirect(url_for("checkout_comprar_agora", evento_id=evento.id))

                    venda = Venda.create(utilizador=g.utilizador, evento=evento, total=lugar.preco_base)
                    Bilhete.create(venda=venda, lugar=lugar, preco=lugar.preco_base)
                    lugar.vendido = True
                    lugar.save()
                    Recibo.create(venda=venda, nif=nif, valor_total=lugar.preco_base)

                flash("Compra realizada com sucesso!", "success")
                return redirect(url_for("utilizador"))
            except Exception:
                flash("Erro ao processar a compra.", "danger")

    return render_template("checkout_comprar_agora.html", 
                           evento=evento, 
                           lugar_sugerido=lugar_sugerido, 
                           filas=filas, 
                           lugares=lugares_da_fila, 
                           fila_selecionada=fila_selecionada)

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
            flash("Credenciais inválidas.", "warning")
    return render_template("login.html")


@app.route("/deslogar")
def deslogar():
    if g.utilizador is not None:
        session.pop("user_id", None)
    return redirect(url_for("index"))

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
        flash("Registro bem-sucedido! Por favor, faça login.", "success")
        return redirect(url_for("login"))
    return render_template("registro.html")


@app.route("/carrinho")
def carrinho():
    return render_template("carrinho.html")


@app.route("/eventos")
def eventos():
    filtros = []

    # Subquery para filtrar apenas lugares disponíveis
    lugares_disponiveis = Lugar.select().where(Lugar.vendido == False)

    query = (
        Evento
        .select(
            Evento,
            fn.MIN(Lugar.preco_base).alias("preco_min"),
            fn.MAX(Lugar.preco_base).alias("preco_max"),
        )
        .join(Lugar, JOIN.LEFT_OUTER)
        .where(Lugar.vendido == False)  # Apenas lugares disponíveis
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
        flash("Precisa de iniciar sessão para aceder ao perfil.", "warning")
        return redirect(url_for("login"))
    
    vendas = Venda.select().where(Venda.utilizador == g.utilizador)
    encomendas = []

    for venda in vendas:
        bilhetes = venda.bilhetes  # todos os bilhetes dessa venda
        quantidade = bilhetes.count()
        valor_total = float(venda.total)
        data_encomenda = venda.data_venda.strftime("%d/%m/%Y")
        estado = "Confirmado"  # podes adicionar lógica de estado
        evento_titulo = venda.evento.titulo

        # Buscar recibo ligado à venda
        recibo = Recibo.get_or_none(Recibo.venda == venda)
        nif = recibo.nif if recibo else "-"
        valor_recibo = float(recibo.valor_total) if recibo else "-"

        encomendas.append({
            "evento_titulo": evento_titulo,
            "data_encomenda": data_encomenda,
            "quantidade": quantidade,
            "valor_total": valor_total,
            "estado": estado,
            "nif": nif,
            "valor_recibo": valor_recibo
        })

    return render_template("utilizador.html", utilizador=g.utilizador, encomendas=encomendas)


@app.route("/apagar_conta", methods=["POST"])
def apagar_conta():
    if g.utilizador is None:
        flash("Precisa de iniciar sessão para apagar a conta.", "warning")
        return redirect(url_for("login"))

    user = g.utilizador
    session.pop("user_id", None)
    user.delete_instance()
    flash("Conta apagada com sucesso.", "success")
    return redirect(url_for("login"))

@app.route("/editar_conta", methods=["POST"])
def editar_conta():
    if g.utilizador is None:
        flash("Precisa de iniciar sessão.", "warning")
        return redirect(url_for("login"))

    user = g.utilizador

    user.nome = request.form["nome"]
    user.email = request.form["email"]
    user.telefone = request.form.get("telefone")
    user.documento_identificacao = request.form.get("documento_identificacao")

    nova_senha = request.form.get("senha")
    if nova_senha:
        user.set_senha(nova_senha)

    user.save()

    flash("Dados atualizados com sucesso.", "success")
    return redirect(url_for("utilizador"))


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

from flask_mail import Message

@app.route("/suporte", methods=["GET", "POST"])
def suporte():
    if request.method == "POST":
        nome = request.form["nome"]
        email = request.form["email"]
        assunto = request.form["assunto"]
        mensagem = request.form["mensagem"]

        msg = Message(
            subject=f"[Suporte] {assunto}",
            recipients=["suporte@eventpy.pt"],
            body=f"""
Nova mensagem de suporte

Nome: {nome}
Email: {email}
Assunto: {assunto}

Mensagem:
{mensagem}
"""
        )

        resposta = Message(
            subject="Recebemos a sua mensagem",
            recipients=[email],
            body="Obrigado pelo contacto. A nossa equipa irá responder em breve."
        )

        mail.send(resposta)
        mail.send(msg)

        flash("Mensagem enviada com sucesso.", "success")
        return redirect(url_for("suporte"))

    return render_template("suporte.html")


if __name__ == "__main__":
    app.run(debug=True)
