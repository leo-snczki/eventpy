import sys
from datetime import datetime
from peewee import *
from database import db
from werkzeug.security import generate_password_hash, check_password_hash

class BaseModel(Model):
    class Meta:
        database = db

class Utilizador(BaseModel):
    nome = CharField()
    email = CharField(unique=True)
    is_admin = BooleanField(default=False)
    telefone = CharField()
    documento_identificacao = CharField()
    senha_hash = CharField()
    criado_em = DateTimeField(default=datetime.now)
    
    def set_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)
    
    def verificar_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)

class Evento(BaseModel):
    TIPO_CONCERTO = "concerto"
    TIPO_TEATRO = "teatros"
    TIPO_PALESTRA = "Palestras"

    TIPOS = (
        (TIPO_CONCERTO, "Concerto"),
        (TIPO_TEATRO, "Teatros"),
        (TIPO_PALESTRA, "Palestras"),
    )
    titulo = CharField()
    descricao = TextField()
    tipo = CharField(choices=TIPOS)
    local = CharField()
    data_hora = DateTimeField()
    duracao = IntegerField(help_text="Duração em minutos")
    capacidade_total = IntegerField(null=True)

class Lugar(BaseModel):
    TIPO_PISTA = "pista"
    TIPO_BANCADA = "bancada"
    TIPO_CAMAROTE = "camarote"

    TIPOS = (
        (TIPO_PISTA, "Pista"),
        (TIPO_BANCADA, "Bancada"),
        (TIPO_CAMAROTE, "Camarote"),
    )

    evento = ForeignKeyField(Evento, backref="lugares", on_delete="CASCADE")
    tipo = CharField(choices=TIPOS)
    fila = CharField(null=True)
    numero = IntegerField(null=True)
    preco_base = DecimalField()
    vendido = BooleanField(default=False) 
    
    def save(self, *args, **kwargs):
        if self.tipo == self.TIPO_PISTA:
            self.fila = None
            self.numero = None
        else:
            if not self.fila or self.numero is None:
                raise ValueError(f"O tipo '{self.tipo}' requer Fila e Número.")
        super().save(*args, **kwargs)

class Venda(BaseModel):
    utilizador = ForeignKeyField(Utilizador, backref="vendas")
    evento = ForeignKeyField(Evento, backref="vendas")
    data_venda = DateTimeField(default=datetime.now)
    total = DecimalField()

class Bilhete(BaseModel):
    venda = ForeignKeyField(Venda, backref="bilhetes")
    lugar = ForeignKeyField(Lugar, null=True)
    preco = DecimalField()

class Recibo(BaseModel):
    venda = ForeignKeyField(Venda)
    data_fatura = DateTimeField(default=datetime.now)
    nif = CharField()
    valor_total = DecimalField()

def init_db():
    db.connect()
    db.create_tables([Utilizador, Evento, Lugar, Venda, Bilhete, Recibo])

def ler_input(msg, tipo=str, obrigatorio=True):
    while True:
        valor = input(msg).strip()
        if not valor and not obrigatorio:
            return None
        if not valor and obrigatorio:
            print("Campo obrigatorio.")
            continue
        try:
            return tipo(valor)
        except ValueError:
            print(f"Valor invalido. Esperado: {tipo.__name__}")

def criar_evento():
    print("\n--- CRIAR NOVO EVENTO ---")
    titulo = ler_input("Titulo do Evento: ")
    
    print("Tipos: [1] Concerto, [2] Teatros, [3] Palestras")
    tipo_map = {"1": "concerto", "2": "teatros", "3": "Palestras"}
    tipo_esc = ""
    while tipo_esc not in tipo_map:
        tipo_esc = input("Selecione o Tipo (1-3): ")
    
    local = ler_input("Local: ")
    
    data_valida = None
    while not data_valida:
        data_str = input("Data e Hora (DD-MM-AAAA HH:MM): ")
        try:
            data_valida = datetime.strptime(data_str, "%d-%m-%Y %H:%M")
        except ValueError:
            print("Formato invalido. Use Dia-Mes-Ano Hora:Minuto")

    duracao = ler_input("Duracao (minutos): ", int)
    
    try:
        evento = Evento.create(
            titulo=titulo,
            descricao=input("Descricao (opcional): ") or "Sem descricao",
            tipo=tipo_map[tipo_esc],
            local=local,
            data_hora=data_valida,
            duracao=duracao
        )
        print(f"Evento '{evento.titulo}' criado com sucesso! ID: {evento.id}")
        input("Pressione Enter para continuar...")
    except Exception as e:
        print(f"Erro ao criar evento: {e}")

def listar_eventos():
    print("\n--- LISTA DE EVENTOS ---")
    eventos = Evento.select()
    if not eventos.count():
        print("Nenhum evento registado.")
        return

    print(f"{'ID':<4} | {'Data':<16} | {'Tipo':<10} | {'Titulo'}")
    print("-" * 50)
    for e in eventos:
        dt_fmt = e.data_hora.strftime("%d/%m/%Y %H:%M")
        print(f"{e.id:<4} | {dt_fmt:<16} | {e.tipo:<10} | {e.titulo}")
    print("-" * 50)

def gerir_lugares():
    listar_eventos()
    evento_id = ler_input("\nID do evento para gerir lugares (0 para voltar): ", int)
    if evento_id == 0: return

    try:
        evento = Evento.get_by_id(evento_id)
    except DoesNotExist:
        print("Evento nao encontrado.")
        return

    print(f"\nGerir Lugares para: {evento.titulo}")
    print("1. Adicionar Lugares de Pista")
    print("2. Adicionar Lugares de Bancada/Camarote")
    
    op = input("Opcao: ")

    match op:
        case "1":
            qtd = ler_input("Quantos bilhetes de pista quer gerar? ", int)
            preco = ler_input("Preco unitario: ", float)
            
            dados = [{'evento': evento, 'tipo': Lugar.TIPO_PISTA, 'preco_base': preco} for _ in range(qtd)]
            with db.atomic():
                Lugar.insert_many(dados).execute()
            print("Lugares de pista criados!")

        case "2":
            tipo_lugar = input("Tipo (bancada/camarote): ").lower()
            fila = ler_input("Letra da Fila: ").upper()
            inicio = ler_input("Numero inicial: ", int)
            fim = ler_input("Numero final: ", int)
            preco = ler_input("Preco unitario: ", float)

            dados = []
            for n in range(inicio, fim + 1):
                dados.append({
                    'evento': evento,
                    'tipo': tipo_lugar,
                    'fila': fila,
                    'numero': n,
                    'preco_base': preco
                })
            
            try:
                with db.atomic():
                    Lugar.insert_many(dados).execute()
                print(f"Lugares {fila}{inicio} a {fila}{fim} criados!")
            except IntegrityError:
                print(f"Erro: Alguns lugares na Fila {fila} ja existem para este evento.")
                print("Operacao cancelada para evitar duplicados.")

        case _:
            print("Opcao invalida.")

def menu_principal():
    init_db()
    while True:
        print("\n" + "="*30)
        print("   GESTOR DE EVENTOS CLI")
        print("="*30)
        print("1. Listar Eventos")
        print("2. Criar Novo Evento")
        print("3. Gerir Lugares / Stock")
        print("4. Sair")
        
        escolha = input("\nEscolha uma opcao: ")

        match escolha:
            case '1':
                listar_eventos()
                input("Pressione Enter para voltar...")
            case '2':
                criar_evento()
            case '3':
                gerir_lugares()
            case '4':
                print("A sair...")
                sys.exit()
            case _:
                print("Opcao invalida.")

if __name__ == "__main__":
    menu_principal()