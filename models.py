from peewee import *
from database import db
from datetime import datetime

class BaseModel(Model):
    class Meta:
        database = db

class Utilizador(BaseModel):
    nome = CharField()
    email = CharField(unique=True)
    telefone = CharField()
    documento_identificacao = CharField()
    criado_em = DateTimeField(default=datetime.now)

class Evento(BaseModel):
    titulo = CharField()
    descricao = TextField()
    local = CharField()
    data_hora = DateTimeField()
    duracao = IntegerField()
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
    vendido = BooleanField(default=False) # 0 para livre, 1 para ocupado, mais leve q usar string ou enum/check
    
    def save(self, *args, **kwargs):
        if self.tipo == self.TIPO_PISTA:
            self.fila = None
            self.numero = None
        else:
            if not self.fila or self.numero is None:
                raise ValueError("Bancada precisa de fila e numero")

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


