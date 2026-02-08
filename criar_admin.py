from models import Utilizador

email = input("Qual o email do admin? ")
try:
    user = Utilizador.get(Utilizador.email == email)
    user.is_admin = True
    user.save()
    print(f"Sucesso! {user.nome} agora é administrador.")
except Utilizador.DoesNotExist:
    print("Utilizador não encontrado.")