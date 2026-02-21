# Claude Vault Memory

Mémoire unifiée NAS pour **Claude Code + Codex + OpenClaw**.

Ce repo a été réorganisé pour séparer clairement:

- `production NAS` (actif)
- `legacy local` (archivé)

## Ce qui est actif en production

### 1) Couche NAS (orchestration moderne)

- `nas_memory/` contient l'API, le worker, la DB SQLite WAL, la sécurité, la couche profil/relations, le graph UI, et le burn-in.
- Entrées principales:
  - `nas_memory/api.py`
  - `nas_memory/worker.py`
  - `nas_memory/db.py`
  - `nas_memory/graph_view.py`
  - `nas_memory/relation_linker.py`

### 2) Moteur core (encore requis)

Ces scripts racine sont **toujours utilisés** par `nas_memory` via subprocess:

- `vault_retrieve.py`
- `process_queue.py`
- `vault_embed.py`

Ils restent donc au root pour la compatibilité runtime actuelle (V1.3R).

## Ce qui est archivé (legacy local)

Le pipeline local historique a été déplacé dans `legacy_local/`:

- `legacy_local/enqueue.py`
- `legacy_local/vault_session_brief.py`
- `legacy_local/vault_status.py`
- `legacy_local/vault_reflect.py`
- `legacy_local/install.sh`
- `legacy_local/launchd/`
- `legacy_local/README_LOCAL_LEGACY.md` (ancienne doc complète)

Ce dossier n'est plus le chemin recommandé pour la prod NAS.

## Structure du repo

- `nas_memory/` → stack multi-agent active (prod)
- `vault_retrieve.py` → retrieval core appelé par API NAS
- `process_queue.py` → consolidation core appelée par worker NAS
- `vault_embed.py` → indexing core appelé par worker/API NAS
- `tests/` → tests core historiques
- `legacy_local/` → ancien mode local Claude-only

## Documentation à suivre

- Mode prod NAS: `nas_memory/README.md`
- Burn-in et gates: `nas_memory/burnin/README.md`
- Ancienne doc locale: `legacy_local/README_LOCAL_LEGACY.md`

## Déploiement NAS (résumé)

```bash
cd /volume1/Services

git clone https://github.com/tofunori/Claude-Vault-Memory.git memory
cd memory

python3 -m venv .venv
source .venv/bin/activate
pip install -r nas_memory/requirements.txt

# config override (optionnel mais recommandé)
# - root config.py non versionné
# - ou MEMORY_CORE_CONFIG=<path>

systemctl --user enable --now memory-api.service memory-worker.service
systemctl --user enable --now memory-profile-compact.timer memory-relation-compact.timer
```

## État d'architecture

- Source de vérité: NAS
- Clients: thin-call only (`/retrieve`, `/events`)
- Écriture mémoire: single-writer (`memory-worker`)
- Relation compaction: shadow/write via flags d'env

