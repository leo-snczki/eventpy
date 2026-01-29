from database import db
from models import Utilizador, Evento, Lugar, Venda, Bilhete, Recibo

db.connect()
db.create_tables([Utilizador, Evento, Lugar, Venda, Bilhete, Recibo])
db.close()
