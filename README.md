A# MANUAL DE INSTALAÇÃO
## Sistema de Monitoria – Windows 10/11

**Versão:** 1.0  
**Sistema operacional:** Windows 10 ou Windows 11

---

## 1. Apresentação

Este manual apresenta os procedimentos necessários para instalar, configurar e executar o Sistema de Monitoria em computadores com Windows.

O sistema foi desenvolvido utilizando Python e Django, com banco de dados MySQL. Seu objetivo é permitir o gerenciamento e o agendamento de atendimentos de monitoria entre alunos e monitores.

## 2. Requisitos necessários

Antes de iniciar a instalação, verifique se o computador possui os seguintes requisitos:

- Windows 10 ou Windows 11;
- Conexão com a internet;
- Python instalado;
- MySQL Server 8.4 ou superior;
- Git instalado (para baixar o projeto).

## 3. Instalação dos programas necessários

### 3.1. Instalação do Python

1. Acesse o site oficial: https://www.python.org/downloads/
2. Baixe uma versão compatível com o projeto.
3. Execute o instalador.
4. Marque a opção **Add Python to PATH**.
5. Clique em Install Now.
6. Após a instalação, abra o PowerShell e execute:

```powershell
python --version
```

Se a versão do Python for exibida, a instalação foi realizada corretamente.

### 3.2. Instalação do MySQL

1. Acesse: https://dev.mysql.com/downloads/installer/
2. Baixe o MySQL Installer.
3. Execute o instalador.
4. Selecione a instalação do MySQL Server.
5. Configure a senha do usuário administrador (root).
6. Finalize a instalação e mantenha o serviço MySQL em execução.

Recomenda-se instalar também o MySQL Workbench para facilitar o gerenciamento do banco de dados.

### 3.3. Instalação do Git

1. Acesse: https://git-scm.com/downloads/win
2. Baixe o instalador para Windows.
3. Execute a instalação utilizando as configurações recomendadas.
4. Abra o PowerShell e execute:

```powershell
git --version
```

Se a versão for exibida, o Git está instalado corretamente.

## 4. Baixando o projeto

O projeto deve ser obtido por meio do repositório Git da equipe.

1. Abra o GitHub e acesse o repositório do Sistema de Monitoria.
2. Copie o endereço HTTPS do repositório.
3. Abra o PowerShell.
4. Escolha uma pasta para armazenar o projeto.
5. Execute:

```powershell
git clone ENDERECO_DO_REPOSITORIO
```

Substitua `ENDERECO_DO_REPOSITORIO` pelo endereço copiado do GitHub.

Entre na pasta criada:

```powershell
cd SistemaMonitoria
```

Observação: o nome da pasta pode variar conforme o repositório.

## 5. Configuração do ambiente virtual

O ambiente virtual permite instalar as dependências do projeto sem interferir em outras instalações do Python.

Dentro da pasta principal do projeto, execute:

```powershell
python -m venv venv
```

Ative o ambiente virtual:

```powershell
.\venv\Scripts\Activate.ps1
```

Caso o PowerShell bloqueie a execução do script, execute:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Depois, tente ativar novamente:

```powershell
.\venv\Scripts\Activate.ps1
```

A indicação `(venv)` deverá aparecer no início da linha do terminal.

## 6. Instalação das dependências

Com o ambiente virtual ativado, instale as bibliotecas utilizadas pelo projeto.

Se o repositório possuir um arquivo `requirements.txt`, execute:

```powershell
pip install -r requirements.txt
```

Caso o arquivo não exista, as dependências deverão ser instaladas conforme as configurações do projeto.

## 7. Configuração do banco de dados

Abra o MySQL Workbench e conecte-se ao servidor local.

Crie o banco de dados utilizado pelo sistema:

```sql
CREATE DATABASE sistema_monitoria
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;
```

Configure as credenciais de acesso ao banco de dados no arquivo `.env`, conforme os parâmetros utilizados pelo projeto.

Exemplo de configuração:

```env
DB_NAME=sistema_monitoria
DB_USER=root
DB_PASSWORD=sua_senha
DB_HOST=localhost
DB_PORT=3306
```

**Importante:** os nomes das variáveis devem corresponder aos utilizados no arquivo de configuração do Django. Não compartilhe senhas ou credenciais no repositório GitHub.

## 8. Executando as migrações

As migrações criam as tabelas necessárias no banco de dados.

Com o ambiente virtual ativado e o banco de dados configurado, execute:

```powershell
python manage.py migrate
```

Para verificar se todas as migrações foram aplicadas corretamente, execute:

```powershell
python manage.py showmigrations
```

## 9. Inicialização do sistema

Para iniciar o servidor local, execute:

```powershell
python manage.py runserver
```

Após a inicialização, abra um navegador e acesse:

http://127.0.0.1:8000/

A página inicial do Sistema de Monitoria deverá ser apresentada.

## 10. Encerramento do sistema

Para encerrar o servidor, retorne ao terminal e pressione:

`CTRL + C`

Para desativar o ambiente virtual, execute:

```powershell
deactivate
```

## 11. Solução de problemas comuns

| Problema | Possível solução |
|---|---|
| Python não reconhecido | Verificar a instalação e a variável PATH. |
| Ambiente virtual não ativa | Verificar se está na pasta principal do projeto e utilizar `.\venv\Scripts\Activate.ps1`. |
| Erro de conexão com MySQL | Verificar se o serviço MySQL está em execução e conferir as credenciais. |
| Banco de dados desconhecido | Criar o banco de dados com o nome configurado no projeto. |
| Módulo não encontrado | Ativar o ambiente virtual e instalar as dependências. |
| Página não abre | Verificar se o servidor Django está em execução. |

## 12. Considerações finais

Após seguir todos os procedimentos, o Sistema de Monitoria estará instalado e poderá ser executado localmente no computador.

Para utilizar o sistema novamente, basta abrir o terminal na pasta do projeto, ativar o ambiente virtual e executar o servidor Django.

**Comandos principais para iniciar o sistema após a instalação:**

```powershell
cd caminho\do\SistemaMonitoria

.\venv\Scripts\Activate.ps1

python manage.py runserver
```

O sistema estará disponível em http://127.0.0.1:8000/.