from __future__ import annotations

from collections import defaultdict

from app.infrastructure.providers.contracts import (
    ProviderAdapter,
    ProviderCapability,
    ProviderDescriptor,
)


class ProviderRegistryError(ValueError):
    pass


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ProviderAdapter] = {}
        self._descriptors: dict[str, ProviderDescriptor] = {}

    def register(
        self, provider: ProviderAdapter, descriptor: ProviderDescriptor | None = None
    ) -> None:
        name = provider.name
        if name in self._providers:
            raise ProviderRegistryError(f"Provider already registered: {name}")
        descriptor = descriptor or ProviderDescriptor(name, provider.capabilities)
        if descriptor.name != name:
            raise ProviderRegistryError("Descriptor name must match provider name")
        self._providers[name] = provider
        self._descriptors[name] = descriptor

    def get(self, name: str) -> ProviderAdapter:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise ProviderRegistryError(f"Unknown provider: {name}") from exc

    def candidates(self, capability: ProviderCapability) -> list[ProviderDescriptor]:
        return sorted(
            (d for d in self._descriptors.values() if d.enabled and capability in d.capabilities),
            key=lambda d: d.priority,
        )

    def providers_by_capability(self) -> dict[ProviderCapability, list[str]]:
        result: dict[ProviderCapability, list[str]] = defaultdict(list)
        for descriptor in self._descriptors.values():
            if descriptor.enabled:
                for capability in descriptor.capabilities:
                    result[capability].append(descriptor.name)
        return dict(result)
