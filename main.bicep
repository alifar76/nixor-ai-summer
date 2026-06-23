// main.bicep — everything ONE student (or pair) gets in their resource group.
// Deployed at resource-group scope by infra/provision_student.py.
//
// Cost safety is built in here, because Azure budgets only ALERT, they don't STOP:
//   • Azure OpenAI capacity (TPM) is capped low via `openAiCapacity`.
//   • Hosting uses the free F1 tier.
//   • No VMs, no GPUs, no provisioned throughput anywhere.

@description('Azure region. Verify gpt-4o-mini is available here before deploying.')
param location string = resourceGroup().location

@description('Short team/student identifier, e.g. team01. Lowercase, hyphen-safe.')
param team string

@description('Model to deploy.')
param modelName string = 'gpt-4o-mini'

@description('Model version. Verify against your region/subscription.')
param modelVersion string = '2024-07-18'

@description('Deployment capacity in thousands of tokens-per-minute. KEEP THIS LOW — it is the real cost cap.')
@minValue(1)
@maxValue(20)
param openAiCapacity int = 5

@description('App Service SKU. F1 = free. Use B1 only temporarily (e.g. demo day) if apps must stay warm.')
@allowed([ 'F1', 'B1' ])
param appServiceSku string = 'F1'

@description('Date this sandbox should be torn down. Used as a tag for easy cleanup.')
param expires string = '2026-09-01'

var openAiName = '${team}-openai'
var planName = '${team}-plan'
var webAppName = '${team}-app'
var deploymentName = modelName

var commonTags = {
  course: 'nixor-ai-cloud'
  team: team
  expires: expires
}

// ---- Azure OpenAI (Cognitive Services) -----------------------------------
resource openai 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: openAiName
  location: location
  tags: commonTags
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: openAiName
    publicNetworkAccess: 'Enabled'
  }
}

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openai
  name: deploymentName
  sku: {
    name: 'Standard'
    capacity: openAiCapacity // thousands of TPM — the hard rate cap
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
  }
}

// ---- App Service (free tier) to host the student's Streamlit app ----------
resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: planName
  location: location
  tags: commonTags
  kind: 'linux'
  sku: { name: appServiceSku }
  properties: { reserved: true }
}

resource webApp 'Microsoft.Web/sites@2024-04-01' = {
  name: webAppName
  location: location
  tags: commonTags
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      // Streamlit needs an explicit start command and port.
      appCommandLine: 'python -m streamlit run app.py --server.port 8000 --server.address 0.0.0.0'
      appSettings: [
        { name: 'WEBSITES_PORT', value: '8000' }
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
        { name: 'AZURE_OPENAI_ENDPOINT', value: openai.properties.endpoint }
        // NOTE: key-in-app-setting is fine for a class. The "best practice" upgrade
        // (worth showing students in Session 4) is a Key Vault reference or a
        // managed identity so the key never appears anywhere. See CLAUDE.md.
        { name: 'AZURE_OPENAI_API_KEY', value: openai.listKeys().key1 }
        { name: 'AZURE_OPENAI_DEPLOYMENT', value: deploymentName }
        { name: 'AZURE_OPENAI_API_VERSION', value: '2024-10-21' }
      ]
    }
  }
}

// ---- Outputs the platform shows the student / stores in its DB ------------
output openAiEndpoint string = openai.properties.endpoint
output webAppName string = webApp.name
output webAppUrl string = 'https://${webApp.properties.defaultHostName}'
output deploymentName string = deploymentName
