import os
import io
import base64
import qrcode
from xhtml2pdf import pisa
from flask import Flask, g, render_template, request, redirect, url_for, session, flash, make_response
from flask_bootstrap import Bootstrap5
from flask_mail import Mail, Message
from datetime import datetime
from models import Recibo, Utilizador, Evento, Lugar, Venda, Bilhete, db
from dotenv import load_dotenv
from peewee import *
from functools import wraps

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

            if "carrinho" not in session:
                session["carrinho"] = []
            g.carrinho_count = len(session.get("carrinho", [])) # se n tiver, da erro ao renderizar no index se n tiver logado.

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
        session.clear()
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
        estado = "Confirmado"
        evento_titulo = venda.evento.titulo

        recibo = Recibo.get_or_none(Recibo.venda == venda)
        nif = recibo.nif if recibo else "-"

        encomendas.append({
            "venda_id": venda.id,
            "evento_titulo": evento_titulo,
            "data_encomenda": data_encomenda,
            "quantidade": quantidade,
            "valor_total": valor_total,
            "estado": estado,
            "nif": nif,
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
        flash("Inicie sessão para escolher o seu lugar.", "warning")
        return redirect(url_for("login"))

    evento = Evento.get_or_none(Evento.id == evento_id)
    if not evento:
        return redirect(url_for("eventos"))

    if request.method == "POST":
        selecionados = request.form.getlist("lugares_selecionados")
        if not selecionados:
            flash("Selecione pelo menos um lugar.", "warning")
        else:
            carrinho = session.get("carrinho", [])
            for sid in selecionados:
                sid_int = int(sid)
                if sid_int not in carrinho:
                    carrinho.append(sid_int)
            session["carrinho"] = carrinho
            session.modified = True
            flash("Adicionado com sucesso!", "success")
            return redirect(url_for("carrinho"))

    # Lógica de carregar filas e lugares (GET)
    fila_selecionada = request.args.get("fila")
    filas_query = (Lugar.select(Lugar.fila)
                   .where((Lugar.evento == evento) & (Lugar.vendido == False) & (Lugar.fila.is_null(False)))
                   .distinct().order_by(Lugar.fila))
    filas = [f.fila for f in filas_query]
    
    lugares = []
    if fila_selecionada:
        lugares = Lugar.select().where((Lugar.evento == evento) & (Lugar.fila == fila_selecionada))

    return render_template("escolher_lugar.html", evento=evento, filas=filas, 
                           fila_selecionada=fila_selecionada, lugares=lugares)

@app.route("/adicionar_carrinho/<int:evento_id>")
def adicionar_carrinho(evento_id):
    if g.utilizador is None:
        flash("Precisa de iniciar sessão para comprar.", "warning")
        return redirect(url_for("login"))

    evento = Evento.get_or_none(Evento.id == evento_id)
    if not evento:
        flash("Evento não encontrado.", "danger")
        return redirect(url_for("eventos"))

    # Concerto adiciona o lugar de pista mais barato direto
    if evento.tipo == Evento.TIPO_CONCERTO:
        lugar = (Lugar.select()
                 .where((Lugar.evento == evento) & (Lugar.tipo == Lugar.TIPO_PISTA) & (Lugar.vendido == False))
                 .order_by(Lugar.preco_base.asc()).first())
        
        if not lugar:
            flash("Desculpe, este concerto está esgotado.", "warning")
            return redirect(url_for("eventos"))

        carrinho = session.get("carrinho", [])
        if lugar.id not in carrinho:
            carrinho.append(lugar.id)
            session["carrinho"] = carrinho
            session.modified = True
            flash(f"Bilhete para {evento.titulo} adicionado ao carrinho!", "success")
        else:
            flash("Este bilhete já está no seu carrinho.", "info")

        session["carrinho"] = carrinho
        session.modified = True
        return redirect(url_for("carrinho"))

    # Outros tipos (Teatro/Palestra) mandam escolher lugar
    return redirect(url_for("escolher_lugar", evento_id=evento.id))

@app.route("/remover_carrinho/<int:lugar_id>")
def remover_carrinho(lugar_id):
    carrinho = session.get("carrinho", [])
    if lugar_id in carrinho:
        carrinho.remove(lugar_id)
        session["carrinho"] = carrinho
        session.modified = True
    return redirect(url_for("carrinho"))



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

@app.route("/compras/bilhetes/<int:venda_id>")
def ver_bilhetes(venda_id):
    if g.utilizador is None:
        return redirect(url_for("login"))

    venda = Venda.get_or_none((Venda.id == venda_id) & (Venda.utilizador == g.utilizador))
    if not venda:
        flash("Venda não encontrada.", "danger")
        return redirect(url_for("utilizador"))

    bilhetes_info = []
    for b in venda.bilhetes:
        # Dados para o QR Code ID do bilhete com hash fictício
        # Na vida real, usaria um token único seguro.
        dados_qr = f"BILHETE-{b.id}-EVENTO-{venda.evento.id}"
        
        qr = qrcode.make(dados_qr)
        buf = io.BytesIO()
        qr.save(buf, format='PNG')
        img_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        
        lugar_desc = "Pista"
        if b.lugar and b.lugar.tipo != Lugar.TIPO_PISTA:
            lugar_desc = f"{b.lugar.tipo.capitalize()} - Fila {b.lugar.fila}, Lugar {b.lugar.numero}"

        bilhetes_info.append({
            "id": b.id,
            "lugar": lugar_desc,
            "preco": b.preco,
            "qr_code": img_b64
        })

    return render_template("ver_bilhetes.html", venda=venda, bilhetes=bilhetes_info)

@app.route("/compras/fatura/<int:venda_id>")
def download_fatura(venda_id):
    if g.utilizador is None:
        return redirect(url_for("login"))

    venda = Venda.get_or_none((Venda.id == venda_id) & (Venda.utilizador == g.utilizador))
    if not venda:
        return redirect(url_for("utilizador"))
    
    recibo = Recibo.get_or_none(Recibo.venda == venda)

    total_pago = float(venda.total)
    v_base = total_pago / 1.23
    v_iva = total_pago - v_base

    html = render_template(
        "fatura_pdf.html", 
        venda=venda, 
        recibo=recibo, 
        hoje=datetime.now(),
        valor_base=v_base,
        valor_iva=v_iva
    )
    
    pdf_output = io.BytesIO()
    pisa_status = pisa.CreatePDF(io.BytesIO(html.encode("utf-8")), dest=pdf_output)

    if pisa_status.err:
        flash("Erro ao gerar PDF.", "danger")
        return redirect(url_for("utilizador"))

    pdf_output.seek(0)
    response = make_response(pdf_output.read())
    response.headers['Content-Type'] = 'application/pdf'
    filename = f"Fatura_{venda.id}.pdf"
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    
    return response

@app.route("/carrinho")
def carrinho():
    ids = session.get("carrinho", [])
    itens = Lugar.select(Lugar, Evento).join(Evento).where(Lugar.id << ids) if ids else []
    total = sum(item.preco_base for item in itens)
    return render_template("carrinho.html", itens=itens, total=total)

@app.route("/carrinho/finalizar", methods=["POST"])
def finalizar_carrinho():
    if g.utilizador is None:
        flash("Precisa de iniciar sessão para finalizar a compra.", "warning")
        return redirect(url_for("login"))

    ids_carrinho = session.get("carrinho", [])
    if not ids_carrinho:
        flash("O seu carrinho está vazio.", "warning")
        return redirect(url_for("eventos"))

    nif = request.form.get("nif")
    if not nif or len(nif) != 9:
        flash("Por favor, insira um NIF válido com 9 dígitos.", "danger")
        return redirect(url_for("carrinho"))

    try:
        with db.atomic():
            lugares = Lugar.select().where(Lugar.id << ids_carrinho)
            
            for l in lugares:
                if l.vendido:
                    flash(f"O lugar {l.numero if l.numero else ''} do evento {l.evento.titulo} já foi vendido.", "danger")
                    return redirect(url_for("carrinho"))

            itens_por_evento = {}
            for l in lugares:
                evento_id = l.evento.id
                if evento_id not in itens_por_evento:
                    itens_por_evento[evento_id] = []
                itens_por_evento[evento_id].append(l)

            for evento_id, lista_lugares in itens_por_evento.items():
                
                total_evento = sum(l.preco_base for l in lista_lugares)
                evento_obj = lista_lugares[0].evento # Todos nesta lista são do mesmo evento agora

                venda = Venda.create(
                    utilizador=g.utilizador, 
                    evento=evento_obj, 
                    total=total_evento
                )

                for l in lista_lugares:
                    Bilhete.create(venda=venda, lugar=l, preco=l.preco_base)
                    l.vendido = True
                    l.save()

                Recibo.create(venda=venda, nif=nif, valor_total=total_evento)

        session["carrinho"] = []
        flash("Compra finalizada com sucesso! Pode consultar os seus bilhetes no perfil.", "success")
        return redirect(url_for("utilizador"))

    except Exception as e:
        print(f"Erro no checkout: {e}")
        flash("Ocorreu um erro ao processar o seu pedido.", "danger")
        return redirect(url_for("carrinho"))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.utilizador is None or not g.utilizador.is_admin:
            flash("Acesso não autorizado.", "danger")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/admin")
@admin_required
def admin_dashboard():
    # Estatísticas simples
    total_vendas = Venda.select().count()
    total_receita = Venda.select(fn.SUM(Venda.total)).scalar() or 0
    total_users = Utilizador.select().count()
    eventos = Evento.select().order_by(Evento.data_hora.desc())
    
    return render_template("admin/dashboard.html", 
                           total_vendas=total_vendas, 
                           total_receita=total_receita,
                           total_users=total_users,
                           eventos=eventos)

@app.route("/admin/evento/novo", methods=["GET", "POST"])
@admin_required
def admin_novo_evento():
    if request.method == "POST":
        try:
            # Converter data string para objeto datetime
            data_str = request.form["data_hora"] # Formato HTML datetime-local: YYYY-MM-DDTHH:MM
            data_obj = datetime.strptime(data_str, "%Y-%m-%dT%H:%M")
            
            Evento.create(
                titulo=request.form["titulo"],
                descricao=request.form["descricao"],
                tipo=request.form["tipo"],
                local=request.form["local"],
                data_hora=data_obj,
                duracao=int(request.form["duracao"])
            )
            flash("Evento criado com sucesso!", "success")
            return redirect(url_for("admin_dashboard"))
        except Exception as e:
            flash(f"Erro ao criar evento: {e}", "danger")
            
    return render_template("admin/form_evento.html", evento=None)

@app.route("/admin/evento/editar/<int:evento_id>", methods=["GET", "POST"])
@admin_required
def admin_editar_evento(evento_id):
    evento = Evento.get_or_none(Evento.id == evento_id)
    if not evento:
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        try:
            data_str = request.form["data_hora"]
            evento.data_hora = datetime.strptime(data_str, "%Y-%m-%dT%H:%M")
            
            evento.titulo = request.form["titulo"]
            evento.descricao = request.form["descricao"]
            evento.tipo = request.form["tipo"]
            evento.local = request.form["local"]
            evento.duracao = int(request.form["duracao"])
            evento.save()
            
            flash("Evento atualizado!", "success")
            return redirect(url_for("admin_dashboard"))
        except Exception as e:
            flash(f"Erro: {e}", "danger")

    return render_template("admin/form_evento.html", evento=evento)

@app.route("/admin/evento/apagar/<int:evento_id>", methods=["POST"])
@admin_required
def admin_apagar_evento(evento_id):
    evento = Evento.get_or_none(Evento.id == evento_id)
    if evento:
        evento.delete_instance()
        flash("Evento apagado.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/evento/<int:evento_id>/lugares", methods=["GET", "POST"])
@admin_required
def admin_gerir_lugares(evento_id):
    evento = Evento.get_or_none(Evento.id == evento_id)
    if not evento: return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        acao = request.form.get("acao")
        preco = float(request.form.get("preco"))
        
        try:
            with db.atomic():
                if acao == "pista":
                    qtd = int(request.form.get("quantidade"))
                    dados = [{'evento': evento, 'tipo': Lugar.TIPO_PISTA, 'preco_base': preco} for _ in range(qtd)]
                    Lugar.insert_many(dados).execute()
                    flash(f"{qtd} lugares de pista adicionados!", "success")

                elif acao == "sentado":
                    tipo_lugar = request.form.get("tipo_lugar") # bancada ou camarote
                    fila = request.form.get("fila").upper()
                    inicio = int(request.form.get("inicio"))
                    fim = int(request.form.get("fim"))
                    
                    dados = []
                    for n in range(inicio, fim + 1):
                        dados.append({
                            'evento': evento, 
                            'tipo': tipo_lugar, 
                            'fila': fila, 
                            'numero': n, 
                            'preco_base': preco
                        })
                    Lugar.insert_many(dados).execute()
                    flash(f"Lugares {fila}{inicio}-{fim} adicionados!", "success")
                    
        except IntegrityError:
            flash("Erro: Lugares duplicados ou dados inválidos.", "danger")
        except Exception as e:
            flash(f"Erro: {e}", "danger")
            
        return redirect(url_for("admin_gerir_lugares", evento_id=evento.id))

    # Resumo dos lugares atuais
    total_lugares = Lugar.select().where(Lugar.evento == evento).count()
    lugares_vendidos = Lugar.select().where((Lugar.evento == evento) & (Lugar.vendido == True)).count()
    
    return render_template("admin/gerir_lugares.html", 
                           evento=evento, 
                           total=total_lugares, 
                           vendidos=lugares_vendidos)

if __name__ == "__main__":
    app.run(debug=True)
