---
type: component
title: "Bensyne — Component Level (Hexagonal Layers)"
c4_level: component
system: bensyne
createdAt: "2026-08-11T00:00:00Z"
updatedAt: "2026-08-11T00:00:00Z"
tags: [component, architecture, hexagonal]
see_also:
  - "architectures/bensyne/0001-container.architecture.md"
  - "concepts/0003-memory-bank-aggregate.concept.md"
  - "concepts/0002-memory-domain.concept.md"
  - "specifications/0001-bensyne-ddd-migration.spec.md"
linked_elements:
  - mcp-server
  - use-cases
  - memory-bank-aggregate
  - memory-bank-entity
  - memory-entity
  - file-hash-vo
  - mnemosyne-client
  - hash-index-service
  - result-pattern
---

# Bensyne — Component Level (Hexagonal Layers)

## Diagram

```mermaid
flowchart TB
    subgraph Adapters["◇ Adapters"]
        MCP["FastMCP Server\nMCP protocol entry point — routes tool calls to use cases"]
    end

    subgraph Application["◇ Application"]
        UC["Use Cases\nProcessMemory · RecallMemory · ForgetMemory · UpdateMemory · SleepMemory · ListBanks · RegisterBank"]
    end

    subgraph Domain["◇ Domain"]
        MBA["MemoryBankAggregate\nAggregate root — remember · forget · activate · suspend\nProduces domain events in Result.events"]
        MB["MemoryBank Entity\nname · description · status\n(active/registered/suspended) · memory_count"]
        MEM["Memory Entity\ncontent · importance · scope · source\nveracity · metadata"]
        FH["FileHash Value Object\nSHA-256 hash_value (64 hex chars)\nStandalone — not part of any aggregate"]
    end

    subgraph Infrastructure["◇ Infrastructure"]
        MC["MnemosyneClient\nWraps mnemosyne-oss with Result[T]\nremember · recall · forget · update · sleep · stats"]
        HIS["HashIndexService\nWraps HashIndex with Result[T]\nstore · lookup · remove"]
    end

    MNEM["mnemosyne-oss Library\nExternal memory engine\n(lazy-imported)"]:::ext
    HDB[("HashIndex SQLite DB\nWAL-mode file hash index")]:::db

    MCP -->|"Dispatches tool calls"| UC
    UC -->|"Operates on aggregate"| MBA
    MBA -->|"Composes"| MB
    MBA -->|"Composes List[Memory]"| MEM
    UC -->|"Dedup lookup/store"| HIS
    UC -->|"Persist memories"| MC
    MC -->|"Library calls"| MNEM
    HIS -->|"WAL-mode R/W"| HDB

    classDef ext fill:#f9f2f4,stroke:#d14d72,stroke-width:2px
    classDef db fill:#e8f8f5,stroke:#1abc9c,stroke-width:2px
```

## Elements

| ID | Name | Type | Technology | Description |
|----|------|------|-----------|-------------|
| mcp-server | FastMCP Server | Component | FastMCP | MCP protocol entry point — routes tool calls to use cases |
| use-cases | Use Cases | Component | Python | 7 use cases: ProcessMemory, RecallMemory, ForgetMemory, UpdateMemory, SleepMemory, ListBanks, RegisterBank |
| memory-bank-aggregate | MemoryBankAggregate | Component | Python/frozen dataclass | Aggregate root — orchestrates MemoryBank + List[Memory]; remember, forget, activate, suspend; events in Result.events |
| memory-bank-entity | MemoryBank Entity | Component | Python/frozen dataclass | name (str), description (Optional[str]), status (Status: active/registered/suspended), created_at, last_accessed, memory_count |
| memory-entity | Memory Entity | Component | Python/frozen dataclass | content (str), importance (float 0.0-1.0), source (str), scope (Scope: working/episodic/semantic/suspended), created_at, updated_at, veracity, metadata |
| file-hash-vo | FileHash Value Object | Component | Python/frozen dataclass | hash_value (str, SHA-256, 64 hex chars) — standalone value object, not part of any aggregate |
| mnemosyne-client | MnemosyneClient | Component | Python | Infrastructure adapter — wraps mnemosyne-oss with Result[T]; implements IMnemosyneClient interface |
| hash-index-service | HashIndexService | Component | Python | Infrastructure adapter — wraps HashIndex with Result[T]; implements IHashIndexService interface |
| mnemosyne-lib | mnemosyne-oss Library | Component_Ext | Python | External library — lazy-imported, not a remote service |
| hash-db | HashIndex SQLite DB | ComponentDbExt | SQLite | WAL-mode file hash index — maps SHA-256 hashes to memory IDs |

## Notes

- All domain entities are **frozen dataclasses** (immutable) — updates produce new instances
- Result[T] is the return type for ALL domain operations; domain events live in `Result.events`, not on entities
- MemoryBankAggregate is the **only boundary** for memory operations — remembers can only happen on active banks
- Scope values: working, episodic, semantic, suspended — suspend transitions memory scope to "suspended"
- FileHash is a standalone value object, not part of any aggregate
- Pydantic schemas (`MemorySchema`, `MemoryBankSchema`) are used by entity factory methods (`Memory.of()`, `MemoryBank.of()`)
