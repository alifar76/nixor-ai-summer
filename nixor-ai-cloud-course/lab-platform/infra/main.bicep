@description('Azure region for the platform resources.')
param location string = resourceGroup().location

@description('Web App name (must be globally unique in azurewebsites.net).')
param appName string

@description('App Service plan name.')
param appServicePlanName string = '${appName}-plan'

@description('App Service SKU. B1 recommended for reliability with websockets.')
@allowed([
  'B1'
  'P0v3'
  'P1v3'
])
param appServiceSku string = 'B1'

@description('Azure OpenAI account name.')
param openAiName string = '${appName}-openai'

@description('Model deployment name.')
param modelName string = 'gpt-4.1-mini'

@description('Model version in your subscription/region.')
param modelVersion string = '2025-04-14'

@description('Deployment capacity (thousands of TPM). Keep low for cost control.')
@minValue(1)
@maxValue(20)
param openAiCapacity int = 5

@description('Strong random signing key for JWT sessions.')
@secure()
param sessionSigningKey string

@description('Optional signup gate code.')
param signupAccessCode string = ''

@description('Allowed CORS origins, comma-separated.')
param corsOrigins string = '*'

resource openai 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: openAiName
  location: location
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: openAiName
    publicNetworkAccess: 'Enabled'
  }
}

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  name: modelName
  parent: openai
  sku: {
    name: 'Standard'
    capacity: openAiCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
  }
}

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: appServicePlanName
  location: location
  kind: 'linux'
  sku: {
    name: appServiceSku
    tier: appServiceSku == 'B1' ? 'Basic' : 'PremiumV3'
  }
  properties: {
    reserved: true
  }
}

resource web 'Microsoft.Web/sites@2024-04-01' = {
  name: appName
  location: location
  kind: 'app,linux'
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      appCommandLine: 'bash backend/startup.sh'
      alwaysOn: appServiceSku != 'B1' ? true : false
      appSettings: [
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true'
        }
        {
          name: 'ENABLE_ORYX_BUILD'
          value: 'true'
        }
        {
          name: 'WEBSITES_PORT'
          value: '8000'
        }
        {
          name: 'DATABASE_URL'
          value: 'sqlite:////home/site/data/lab_platform.db'
        }
        {
          name: 'WORKSPACE_DRIVER'
          value: 'local'
        }
        {
          name: 'LOCAL_WORKSPACE_ROOT'
          value: '/home/site/workspaces'
        }
        {
          name: 'TERMINAL_REQUIRE_NON_ROOT'
          value: 'true'
        }
        {
          name: 'LOCAL_SANDBOX_UID'
          value: '1000'
        }
        {
          name: 'LOCAL_SANDBOX_GID'
          value: '1000'
        }
        {
          name: 'TERMINAL_BLOCK_DANGEROUS_COMMANDS'
          value: 'true'
        }
        {
          name: 'SESSION_SIGNING_KEY'
          value: sessionSigningKey
        }
        {
          name: 'SIGNUP_ACCESS_CODE'
          value: signupAccessCode
        }
        {
          name: 'CORS_ORIGINS'
          value: corsOrigins
        }
        {
          name: 'AZURE_OPENAI_ENDPOINT'
          value: openai.properties.endpoint
        }
        {
          name: 'AZURE_OPENAI_API_KEY'
          value: openai.listKeys().key1
        }
        {
          name: 'AZURE_OPENAI_DEPLOYMENT'
          value: modelName
        }
        {
          name: 'AZURE_OPENAI_API_VERSION'
          value: '2024-10-21'
        }
      ]
    }
  }
}

output webAppName string = web.name
output webAppUrl string = 'https://${web.properties.defaultHostName}'
output openAiEndpoint string = openai.properties.endpoint
output modelDeploymentName string = modelDeployment.name
