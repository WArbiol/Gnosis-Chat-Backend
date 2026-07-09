# Guia de Deploy e Autenticação GCP - Gnosis Chat Backend

Este documento descreve como configurar a infraestrutura de deploy do backend em produção no **Google Cloud Run** e como autenticar localmente as APIs de Inteligência Artificial do GCP (**Vertex AI Reranking API** e **Gemini**) sem a necessidade de expor chaves privadas (`.json`) no código ou no servidor.

---

## 💻 1. Desenvolvimento Local (Sem arquivos JSON de chave privada)

Para rodar localmente sem precisar baixar chaves privadas (`.json`) da Conta de Serviço, utilize o mecanismo de **Application Default Credentials (ADC)** da CLI do Google Cloud:

1. Certifique-se de que a CLI do GCP (`gcloud`) está instalada na sua máquina.
2. Execute o comando de login no seu terminal:
   ```bash
   gcloud auth application-default login
   ```
   *Isso abrirá uma janela no navegador para autenticar com a sua conta do Google associada ao projeto GCP.*
3. No arquivo `.env` do backend, remova ou comente a linha `GOOGLE_APPLICATION_CREDENTIALS`.
4. Mantenha apenas o ID do projeto GCP nas variáveis:
   ```env
   GOOGLE_CLOUD_PROJECT="seu-projeto-gcp-id"
   ```
5. Reinicie o servidor do backend. O SDK do Google detectará automaticamente a sessão ativa do seu navegador.

---

## 🚀 2. Deploy em Produção (Google Cloud Run)

O Cloud Run é o ambiente ideal para hospedar a API FastAPI por ser serverless (escala para zero quando inativo, gerando custo zero em momentos sem uso) e pela integração nativa com o IAM do Google Cloud.

### Passo 1: Preparar a Conta de Serviço (IAM)
1. No Console do GCP, vá em **IAM & Admin** > **Service Accounts**.
2. Crie uma Conta de Serviço para a aplicação (ex: `gnosis-chat-backend-sa`).
3. Conceda o seguinte papel (Role) para essa conta de serviço:
   - **Discovery Engine Viewer** (`roles/discoveryengine.viewer`)
   > [!NOTE]  
   > Este papel concede a permissão necessária (`discoveryengine.rankingConfigs.rank`) para reordenar documentos no Reranker da Vertex AI.
4. *Não baixe chaves JSON.*

### Passo 2: Configurar o Cloud Run
Ao configurar o serviço no Cloud Run (pelo Console Web ou CLI):

#### Opção A: Pelo Console Web
1. Vá na página do **Cloud Run** e clique em **Create Service** (ou edite a revisão atual).
2. Vá na aba **Security** (Segurança) e altere o campo **Service Account** da conta padrão do Compute Engine para a sua conta criada: `gnosis-chat-backend-sa`.
3. Na aba **Variables & Secrets**, adicione as seguintes variáveis de ambiente:
   - `GOOGLE_CLOUD_PROJECT` = `seu-projeto-gcp-id`
   - `QDRANT_URL` = `https://seu-cluster-qdrant-cloud.com`
   - `QDRANT_API_KEY` = `sua-api-key-do-qdrant`
4. Clique em **Deploy**.

#### Opção B: Pela CLI do GCP (`gcloud`)
Você pode executar o build e deploy diretamente do terminal do seu projeto:
```bash
gcloud run deploy gnosis-chat-api \
  --source . \
  --service-account="gnosis-chat-backend-sa@seu-projeto-gcp-id.iam.gserviceaccount.com" \
  --set-env-vars GOOGLE_CLOUD_PROJECT="seu-projeto-gcp-id",QDRANT_URL="url-qdrant",QDRANT_API_KEY="api-key" \
  --allow-unauthenticated \
  --region us-central1
```

---

## 🗄️ 3. Banco de Dados Vetorial (Qdrant Cloud)

Para hospedar o banco de vetores de forma gerenciada e sem custos no desenvolvimento:

1. Crie uma conta no [Qdrant Cloud](https://cloud.qdrant.io/).
2. Crie um cluster gratuito (Free Tier).
3. Copie o endpoint do cluster (URL) e crie uma API Key na aba de chaves do console do Qdrant.
4. Injete a URL e a API Key nas variáveis do Cloud Run ou no seu `.env` local.
