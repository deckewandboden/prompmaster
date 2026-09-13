from django.contrib import admin

from .models import (
    MicrosoftCapability,
    MicrosoftTier,
    PromptApplication,
    PromptDefinition,
    PromptField,
    PromptLegacyContract,
    PromptOption,
    PromptPolicySet,
    PromptVersion,
)

for model in (
    MicrosoftTier,
    PromptApplication,
    PromptDefinition,
    PromptPolicySet,
    PromptVersion,
    PromptField,
    PromptOption,
    MicrosoftCapability,
    PromptLegacyContract,
):
    admin.site.register(model)
