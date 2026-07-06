# Intelbras NVR/DVR Backup Pipeline - Guia de Configuração e Uso

Este repositório contém uma automação em lote para extrair gravações de DVRs/NVRs da Intelbras (ou Dahua), convertê-las em MP4 fragmentado (`fMP4`) e sincronizá-las diretamente com o Google Drive de forma resiliente, rápida e econômica em consumo de internet e espaço local.

---

## 🛠️ Requisitos Finais

Para rodar esta automação em qualquer máquina, você precisará de:

1. **SIM Next instalado e rodando:**
   Como as câmeras estão em uma rede externa e utilizam a conexão em nuvem (P2P da Intelbras), o software **SIM Next** precisa estar aberto e logado nos DVRs na máquina de execução. Ele cria pontes TCP locais (loopback proxy) que mapeiam os DVRs remotos para portas locais.
   * **DVR 1:** Mapeado em uma porta local de exemplo (ex: `8001`).
   * **DVR 2:** Mapeado em uma porta local de exemplo (ex: `8002`).

2. **Miniconda ou Anaconda (Python 3.10+):**
   Para gerenciar as dependências isoladas.

3. **Google Drive para Computador instalado:**
   O aplicativo oficial do Google Drive montará seu Drive como um disco rígido do sistema (ex: drive `G:\`).

---

## ⚙️ Instalação Passo a Passo em Qualquer Máquina

### Passo 1: Clonar/Copiar a Pasta
Mova os seguintes arquivos e pastas estruturados para a máquina de destino:
* `batch_downloader.py` (Script de lote)
* `dvr_api.py` (Biblioteca wrapper do SDK)
* `main.py` (Utilitário de testes individual)
* Pasta `NetSDK_Win64` (Contém as DLLs da Intelbras necessárias)
* `.env` (Configurações de credenciais - deve ser criado localmente com base no `.env.example`)

### Passo 2: Criar o Ambiente Python
Abra o terminal do Anaconda/Miniconda e execute os seguintes comandos para recriar o ambiente isolado e instalar as bibliotecas necessárias:
```bash
# Criar o ambiente com Python 3.10
conda create -n intebras python=3.10 -y

# Ativar o ambiente
conda activate intebras

# Instalar as bibliotecas requeridas
pip install python-dotenv static-ffmpeg google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

### Passo 3: Configurar o arquivo `.env`
Crie um arquivo `.env` com base no arquivo `.env.example` e preencha com as portas reais que o seu SIM Next gerou localmente:
```env
# Exemplo de configuração (.env)
DVR1_NAME = DVR_Exemplo_1
DVR1_SN = SN123456789012
DVR1_PORT = 8001

DVR2_NAME = DVR_Exemplo_2
DVR2_SN = SN987654321098
DVR2_PORT = 8002

HOST = 127.0.0.1
Usuario = admin
Senha = sua_senha_aqui

LOCAL_GD_PATH = G:\My Drive\gravacao
```

---

## 🚀 Como Executar

Certifique-se de que o **SIM Next** e o **Google Drive Desktop** estão abertos e logados antes de iniciar.

Abra o terminal conda e execute:
```bash
conda activate intebras
python batch_downloader.py
```

* O script baixará bloco por bloco de 30 minutos em `.dav`.
* Converterá automaticamente cada bloco para `.mp4`.
* Moverá o arquivo para `G:\My Drive\gravacao\[Nome_Da_Camera]\[Data]\[Tempo].mp4`.
* Apagará o arquivo temporário local para economizar disco.
* Se a internet oscilar ou cair, ele entrará em modo de reconexão automática e continuará do exato ponto em que parou assim que o sinal retornar!
