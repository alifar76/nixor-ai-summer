// policy-deny-expensive-skus.bicep
// Guardrail: stop students from creating anything that could run up a bill.
// Assign this at the SUBSCRIPTION or MANAGEMENT GROUP scope that holds the
// student resource groups (deploy with: az deployment sub create ...).
//
// This PREVENTS a whole class of runaway cost — unlike budgets, which only alert.

targetScope = 'subscription'

@description('Resource types students are not allowed to create.')
param deniedResourceTypes array = [
  'Microsoft.Compute/virtualMachines'
  'Microsoft.Compute/virtualMachineScaleSets'
  'Microsoft.Compute/disks'
  'Microsoft.Sql/servers'
  'Microsoft.ContainerService/managedClusters'
]

// Built-in policy definition: "Not allowed resource types"
var notAllowedResourceTypesPolicyId = tenantResourceId(
  'Microsoft.Authorization/policyDefinitions',
  '6c112d4e-5bc7-47ae-a041-ea2d9dccd749'
)

resource denyExpensive 'Microsoft.Authorization/policyAssignments@2024-04-01' = {
  name: 'nixor-deny-expensive'
  properties: {
    displayName: 'Nixor course — deny expensive resource types'
    policyDefinitionId: notAllowedResourceTypesPolicyId
    parameters: {
      listOfResourceTypesNotAllowed: { value: deniedResourceTypes }
    }
    enforcementMode: 'Default' // Default = enforce (deny). 'DoNotEnforce' = audit only.
  }
}

// OPTIONAL next step for Claude Code: add a second assignment using the
// "Allowed locations" built-in policy to restrict sandboxes to one region.
